# TODO: Prioritize all TODOs lol
import boto3
import email
import os
import re
import subprocess
import time

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr

from emails import get_text_from_email, send_confirmation, send_response
from generate_flashcards import generate_page
from networking_dump import generate_todo_list, extract_per_person_summaries, transcribe_audio
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
        with open(local_filepath, "w") as file_handle:
            file_handle.write(data)
    print(f"Written {pretty_filesize(local_filepath)} to {local_filepath}")

    bucket_key = None
    if bool(bucket_name) and bool(bucket_object_prefix):
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
def convert_audio_to_mp4(file_path):
    audio_file = file_path + ".mp4"
    print(f"Running ffmpeg on {file_path} outputting to {audio_file}")
    try:
        # -y to force overwrite in case the file already exists
        subprocess.run(['ffmpeg', '-y', '-i', file_path, audio_file], check=True)
        print(f'Converted file saved as: {audio_file}')
    except subprocess.CalledProcessError as e:
        print(f'ffmpeg error occurred: {e}')
        return None
    return audio_file


def process_transcript(raw_transcript, sender_name=None, reply_to_address=None, object_prefix=None, network_calls=True):
    # Output storage
    # TODO: Use more proper temp fs
    local_output_prefix = f"/tmp/{object_prefix}"

    print(f"Running Sekretar-katka")
    # TODO: Support longer than 3000 word inputs by some smart chunking.
    summaries = extract_per_person_summaries(raw_transcript=raw_transcript)
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
        if network_calls:
            send_response(
                reply_to_address,
                webpage_link=webpage_link,
                attachment_paths=[summaries_filepath],
                people_count=len(summaries),
                todo_count=len(todo_list),
            )
        else:
            print(f"Would have sent email to {reply_to_address} with {webpage_link}")
    # TODO: Get total token usage as a fun fact (probably need to instantiate a singleton openai class wrapper)


def process_email(raw_email, network_calls=True):
    # TODO: Refactor the email processing to another function which returns some custom object maybe
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
        if network_calls:
            send_confirmation(reply_to_address, attachment_file_paths)
        else:
            print(f"would have sent confirmation to {reply_to_address} with {attachment_file_paths}")
    except Exception as err:
        print(f"ERROR: Could not send confirmation to {reply_to_address} cause {err}")

    raw_transcripts = []
    for attachment_num, attachment_file_path in enumerate(attachment_file_paths):
        print(f"Processing attachment {attachment_num} out of {len(attachment_file_paths)}")
        audio_filepath = convert_audio_to_mp4(attachment_file_path)
        if bool(audio_filepath):
            raw_transcripts.append(transcribe_audio(audio_filepath=audio_filepath))

    object_prefix = f"{sender_name}-{run_idempotency_key}"
    object_prefix = re.sub(r'\s', '-', object_prefix)

    # Here we merge all successfully processed
    # * audio attachments
    # * email bodies
    # into one giant transcript.
    email_body_text = get_text_from_email(msg)
    raw_transcripts.append(email_body_text)
    raw_transcript = "\n\n".join(raw_transcripts)
    process_transcript(
        raw_transcript=raw_transcript,
        sender_name=sender_name,
        reply_to_address=reply_to_address,
        object_prefix=object_prefix,
        network_calls=network_calls,
    )


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

    process_email(raw_email=response['Body'].read())


# For local testing without emails or S3, great for bigger refactors.
# TODO: Make this an automated-ish test (although would require further mocking of OpenAI calls from the test_.. stuff)
if __name__ == "__main__":
    OUTPUT_BUCKET_NAME = None
    with open("input/test-email-short", "rb") as handle:
        file_contents = handle.read()
        process_email(file_contents, network_calls=False)
