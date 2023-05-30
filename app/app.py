# TODO: Prioritize all TODOs lol
import boto3
import datetime
import email
import os
import re
import subprocess
import time

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr

from email_utils import create_raw_email_with_attachments
from generate_flashcards import generate_page
from networking_dump import generate_todo_list, networking_dump
from storage_utils import write_to_csv

s3 = boto3.client('s3')

OUTPUT_BUCKET_NAME = "katka-emails-response"  # !make sure different from the input!
STATIC_HOSTING_BUCKET_NAME = "katka-ai-static-pages"
# TODO: Use timestamp from the saved email file so the static pages can be re-generated.
RUN_ID = str(datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
SENDER_EMAIL = "assistant@katka.ai"
DEBUG_RECIPIENT = "petherz@gmail.com"


def send_email(email_address, subject, body_text, attachment_paths=None):
    if not isinstance(email_address, str):
        print(f"email_adress is NOT a string {email_address}, falling back to {DEBUG_RECIPIENT}")
        email_address = DEBUG_RECIPIENT

    ses = boto3.client('ses')
    sender = SENDER_EMAIL
    recipients = list({email_address, DEBUG_RECIPIENT})
    body_html = """<html>
    <head></head>
    <body>
      <h3>""" + subject + """</h3>
      """ + body_text + """
    </body>
    </html>
    """

    # Create the raw email
    raw_email = create_raw_email_with_attachments(subject, body_html, sender, recipients, attachment_paths)

    try:
        print(f"Attempting to send email to {recipients} with attached files {attachment_paths}")
        response = ses.send_raw_email(
            Source=sender,
            Destinations=recipients,
            RawMessage={
                'Data': raw_email.as_string(),
            }
        )
        print(f'Email sent! Message ID: {response["MessageId"]}, Subject: {subject}')
    except Exception as e:
        print(f'Email with subjectL {subject} failed to send. {e}')


def pretty_filesize(file_path):
    return f"{os.path.getsize(file_path) / 1048576:.2f}MB"


def send_confirmation(email_address: str, attachment_file_paths: list):
    if len(attachment_file_paths) == 0:
        subject = "Yo boss - where is the attachment?"
        body_text = (
            "Hello, <br/><br/>Thanks for trying out katka.ai - your personal networking assistant "
            "- aka the backoffice guy/gal who takes care of the admin so that you can focus on what matters.<br />"
            "But yo boss, where is the attachment? I would love to brew you a coffee, but "
            "I ain't real so an emoji would need to do it \u2615 <br />"
            "Remember, any audio-file would do, I can convert stuff myself \U0001F4AA"
            "<h3>Questions?</h3>"
            f"Please contact my supervisors at {DEBUG_RECIPIENT} - thanks - your team at katka.ai"
        )
        send_email(email_address, subject, body_text)
    else:
        file_list = []
        for file_path in attachment_file_paths:
            file_size = pretty_filesize(file_path)
            file_list.append(f"<li>{os.path.basename(file_path)} ({file_size})</li>")
        file_list_str = "<li".join(file_list)

        subject = "Hey boss - got your recording and I am already crunching through it!"
        body_text = (
            "Hello, <br/><br/>Thanks for trying out katka.ai - your personal networking assistant "
            "- aka the backoffice guy/gal who takes care of the admin so that you can focus on what matters.<br />"
            f"Here are the files I have received: <br /><ul>{file_list_str}</ul><br />"
            f"<p>This will take me 2-15mins.</p>"
            "<h3>Questions?</h3>"
            f"Please contact my supervisors at {DEBUG_RECIPIENT} - thanks - your team at katka.ai"
        )
        send_email(email_address, subject, body_text)


def send_response(email_address, webpage_link, attachment_paths, people_count, todo_count):
    subject = "Summaries from your recent networking event are ready for your review!"
    # TODO: Generate with GPT ideally personalized to the transcript.
    body_text = (
        "Hello, <br/><br/>"
        "Sounds you had a blast at your recent event!<br/>"
        f"Good job you:<br/>"
        f"<ul><li> you met {people_count} people</li>"
        f"<li> with {todo_count} follow ups with suggested drafts to spark your new relationships!</li></ul>\n"
        "<h3>What to do next?<h3>"
        f"<ul><li>Access your <a href=\"{webpage_link}\">follow-up draft messages</a></li>"
        "<li>You can 1-click copy the option you like the best, tweak it if needed and send to your new contact.</li>"
        "<li>See attachment for a nice table format of the summaries</li></ul>"
        "<h3>Questions?</h3>"
        f"Please contact my supervisors at {DEBUG_RECIPIENT} - thanks - your team at katka.ai"
    )
    send_email(email_address, subject, body_text, attachment_paths)


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

    for attachment_num, file_path in enumerate(attachment_file_paths):
        object_prefix = f"{sender_name}-{RUN_ID}-{attachment_num}"
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
