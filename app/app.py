# TODO: Prioritize all TODOs lol
import boto3
import email
import os
import re
import subprocess
import time

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr

from emails import send_confirmation, send_response
from generate_flashcards import generate_page
from networking_dump import generate_todo_list, networking_dump
from storage_utils import pretty_filesize, write_to_csv

s3 = boto3.client('s3')

OUTPUT_BUCKET_NAME = "katka-emails-response"  # !make sure different from the input!
STATIC_HOSTING_BUCKET_NAME = "katka-ai-static-pages"


def write_output_to_local_and_bucket(
        data,
        suffix: str,
        local_output_prefix: str,
        content_type: str,
        bucket_name=None,
        bucket_object_prefix=None,
):
    local_filepath = f"{local_output_prefix}{suffix}"
    print(f"Gonna write some data to {local_filepath}")
    # This is kinda hack
    if suffix.endswith(".csv"):
        write_to_csv(data, local_filepath)
    else:
        # TODO: We might need to support binary data
        with open(local_filepath, "w") as handle:
            handle.write(data)
    print(f"Written {pretty_filesize(local_filepath)} to {local_filepath}")

    bucket_key = None
    if bool(bucket_object_prefix):
        bucket_key = f"{bucket_object_prefix}{suffix}"
        print(f"Uploading that data to S3://{bucket_name}/{bucket_key}")
        s3.upload_file(
            local_filepath,
            bucket_name,
            bucket_key,
            ExtraArgs={'ContentType': content_type},
        )

    return local_filepath, bucket_key


# Here object_prefix is used for both local, response attachments and buckets.
def process_file(file_path, sender_name=None, reply_to_address=None, object_prefix=None):
    audio_file = file_path + ".mp4"
    print(f"Running ffmpeg on {file_path} outputting to {audio_file}")
    try:
        # -y to force overwrite in case the file already exists
        subprocess.run(['ffmpeg', '-y', '-i', file_path, audio_file], check=True)
        print(f'Converted file saved as: {audio_file}')
    except subprocess.CalledProcessError as e:
        print(f'FFmpeg Error occurred: {e}')

    # Output storage
    # TODO: Use more proper temp fs
    local_output_prefix = f"/tmp/{object_prefix}"

    # TODO: Make this multi-modal by e.g. also taking the email body.
    #   One-day we should separate out the ffmpeg conversion from the "unstructed text -> structured" part.
    #   (Or support multiple input types)
    print(f"Running Sekretar-katka")
    summaries = networking_dump(audio_file)
    summaries_filepath, _ = write_output_to_local_and_bucket(
        data=summaries,
        suffix="-summaries.csv",
        content_type="text/csv",
        local_output_prefix=local_output_prefix,
        bucket_name=OUTPUT_BUCKET_NAME,
        bucket_object_prefix=object_prefix
    )

    print(f"Running generate todo-list")
    todo_list = generate_todo_list(summaries)
    todo_list_filepath, _ = write_output_to_local_and_bucket(
        data=todo_list,
        suffix="-todo.csv",
        content_type="text/csv",
        local_output_prefix=local_output_prefix,
        bucket_name=OUTPUT_BUCKET_NAME,
        bucket_object_prefix=object_prefix
    )

    print(f"Running generate webpage")
    page_contents = generate_page(sender_name, summaries, todo_list)
    _, bucket_key = write_output_to_local_and_bucket(
        data=page_contents,
        suffix=".html",
        content_type="text/html",
        local_output_prefix=local_output_prefix,
        bucket_name=STATIC_HOSTING_BUCKET_NAME,
        bucket_object_prefix=object_prefix
    )
    # TODO: Heard it's better at https://vercel.com/guides/deploying-eleventy-with-vercel
    webpage_link = f"http://{STATIC_HOSTING_BUCKET_NAME}.s3-website-us-west-2.amazonaws.com/{bucket_key}"

    if reply_to_address is not None:
        send_response(
            reply_to_address,
            webpage_link=webpage_link,
            attachment_paths=[summaries_filepath],
            people_count=len(summaries),
            todo_count=len(todo_list),
        )
    # TODO: Get total token usage as a fun fact (probably need to instantiate a signleton openai class wrapper)


def lambda_handler(event, context):
    print(f"Received Event: {event}")
    # Get the bucket name and file key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    print(f"Bucket: {bucket} Key: {key}")

    # Download the email from S3
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except NoCredentialsError as e:
        print(e)
        return 'Execution failed'

    raw_email = response['Body'].read()
    print(f"Read raw_email body with {len(raw_email)} bytes")

    # Parse the email
    msg = email.message_from_bytes(raw_email)
    from_address = msg.get('From')
    # Parse the address
    sender_name, addr = parseaddr(from_address)
    reply_to_address = msg.get('Reply-To')
    if reply_to_address is None or not isinstance(reply_to_address, str):
        print("No reply-to address provided, falling back to from_address")
        reply_to_address = addr
    print(f"email from {sender_name} ({addr}) reply-to {reply_to_address}")

    # Generate run-id as an idempotency key for re-runs
    if msg['Date']:
        run_idempotency_key = email.utils.parsedate_to_datetime(msg['Date'])
    else:
        print("Could not find 'Date' header in the email, defaulting to `Message-ID`")
        run_idempotency_key = msg['Message-ID']

    # Process the attachments
    attachment_file_paths = []
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        # Get the attachment's filename
        orig_file_name = part.get_filename()
        print(f"Parsing attachment {orig_file_name}")

        if not bool(orig_file_name):
            continue

        # If there is an attachment, save it to a file
        file_name = f"{time.time()}-{orig_file_name}"
        file_path = os.path.join('/tmp/', file_name)
        with open(file_path, 'wb') as f:
            f.write(part.get_payload(decode=True))
        attachment_file_paths.append(file_path)

    try:
        send_confirmation(reply_to_address, attachment_file_paths)
    except Exception as err:
        print(f"ERROR: Could not send confirmation to {reply_to_address} cause {err}")

    # TODO: Merge all attachment transcripts into one input
    for attachment_num, file_path in enumerate(attachment_file_paths):
        object_prefix = f"{sender_name}-{run_idempotency_key}-{attachment_num}"
        object_prefix = re.sub(r'\s', '-', object_prefix)
        process_file(
            file_path=file_path,
            sender_name=sender_name,
            reply_to_address=reply_to_address,
            object_prefix=object_prefix
        )

# TODO: Better local testing with running the container locally and curling it with the request (needs S3 I guess).
# if __name__ == "__main__":
#     attachment_files, row_counts = process_file("input/kubo.mp4")
#     print(f"generated {attachment_files}")
