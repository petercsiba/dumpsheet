# TODO: Prioritize all TODOs lol
import boto3
import datetime
import email
import os
import re
import shutil
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

    # Create the raw email
    raw_email = create_raw_email_with_attachments(subject, body_text, sender, recipients, attachment_paths)

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


def send_confirmation(email_address: str, attachment_file_paths: list):
    if len(attachment_file_paths) == 0:
        subject = "Yo boss - where is the attachment?"
        body_text = (
            "Hello, \n\nThanks for trying out katka.ai - your virtual assistant.\n"
            "Yo boss, where is the attachment? I would love to brew you a coffer, but\n"
            "I as you know I ain't real so an emoji would need to do it \u2615\n\n"
            "Remember, any audio-file would do, I can convert stuff myself \U0001F4AA\n\n"
            f"If you disagree, please contact my supervisor at {DEBUG_RECIPIENT}"
        )
        send_email(email_address, subject, body_text)
    else:
        file_list = []
        for file_path in attachment_file_paths:
            file_size = f"{os.path.getsize(file_path) / 1048576:.2f}MB"
            file_list.append(f"{os.path.basename(file_path)} ({file_size})")
        file_list_str = "\n*".join(file_list)

        subject = "Hey boss - got your recording and I am already crunching through it!"
        body_text = (
            "Hello, \nThanks for trying out katka.ai - your virtual assistant.\n\n"
            f"Here are the files I have received: \n{file_list_str}\n\n"
            f"This will take me 2-15mins, if you don't hear back please contact my supervisor at {DEBUG_RECIPIENT}"
        )
        send_email(email_address, subject, body_text)


def send_response(email_address, webpage_link, attachment_paths, people_count, todo_count):
    subject = "Summaries from your recent networking event are ready for your review!"
    # TODO: Generate with GPT ideally personalized to the transcript.
    body_text = (
        "Hello, \n"
        "Sounds you had a blast at your recent event! \n\n"
        f"Good job - you met {people_count} with {todo_count} suggested follow ups.\n\n"
        "What to do next?"
        f"* Access your <a href=\"{webpage_link}\">flashcards and todolist online</a>"
        "* See attachment for a nice table format of the summaries\n\n"
        "Questions?\n"
        f"Please contact my supervisors at {DEBUG_RECIPIENT}"
    )
    send_email(email_address, subject, body_text, attachment_paths)


def write_output_to_local_and_bucket(data, suffix, local_output_prefix, bucket_object_prefix=None):
    todo_list_filepath = f"{local_output_prefix}-{suffix}.csv"
    write_to_csv(data, todo_list_filepath)

    if bool(bucket_object_prefix):
        print("Writing todo_list to S3")
        s3.upload_file(todo_list_filepath, OUTPUT_BUCKET_NAME, f"{bucket_object_prefix}-{suffix}.csv")

    return todo_list_filepath


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

    print(f"Running Sekretar-katka")
    summaries = networking_dump(audio_file)

    # Output storage
    # TODO: Use more proper temp fs
    local_output_prefix = f"/tmp/{object_prefix}"
    # Unique identifier to support multiple runs of the same file even if attached multiple times
    summaries_filepath = write_output_to_local_and_bucket(summaries, "summaries", local_output_prefix, object_prefix)

    print(f"Running generate todo-list")
    todo_list = generate_todo_list(summaries)
    todo_list_filepath = write_output_to_local_and_bucket(todo_list, "todo", local_output_prefix, object_prefix)

    page_contents = generate_page(sender_name, summaries, todo_list)
    filename = f"{object_prefix}.html"
    print(f"Writing page_contents to S3 ({len(page_contents)}B) bucket {STATIC_HOSTING_BUCKET_NAME}/{filename}")
    s3.upload_file(todo_list_filepath, STATIC_HOSTING_BUCKET_NAME, filename)
    webpage_link = f"http://{STATIC_HOSTING_BUCKET_NAME}.s3-website-us-west-2.amazonaws.com/{filename}"

    if reply_to_address is not None:
        send_response(
            reply_to_address,
            webpage_link=webpage_link,
            attachment_paths=[summaries_filepath],
            people_count=len(summaries),
            todo_count=len(todo_list),
        )
    # TODO: Try to merge summaries and todo_list into one .CSV
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

    send_confirmation(reply_to_address, attachment_file_paths)

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
