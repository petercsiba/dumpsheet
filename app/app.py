# TODO: Prioritize all TODOs lol
import boto3
import datetime
import email
import os
import subprocess
import time

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr

from email_utils import create_raw_email_with_attachments
from networking_dump import generate_todo_list, networking_dump
from storage_utils import write_to_csv

s3 = boto3.client('s3')

OUTPUT_BUCKET_NAME = "katka-emails-response"  # !make sure different from the input!
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
        file_list = "\n".join([f"* {os.path.basename(file_path)}" for file_path in attachment_file_paths])
        subject = "Hey boss - got your recording and I am already crunching through it!"
        body_text = (
            "Hello, \nThanks for trying out katka.ai - your virtual assistant.\n\n"
            f"Here are the files I have received: \n{file_list}\n\n"
            f"This will take me 2-15mins, if you don't hear back please contact my supervisor at {DEBUG_RECIPIENT}"
        )
        send_email(email_address, subject, body_text, attachment_file_paths)


def send_response(email_address, attachment_paths):
    subject = "Summaries from your last event - please take a look at your todos"
    # TODO: Generate with GPT ideally personalized to the transcript.
    body_text = (
        "Hello, \nSounds you had a blast at your recent event! Good job on meeting all those people "
        "- looking forward to hear more stories from your life!"
    )
    send_email(email_address, subject, body_text, attachment_paths)


def process_file(file_path, bucket_object_prefix=None):
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
    local_output_prefix = file_path
    # Unique identifier to support multiple runs of the same file even if attached multiple times

    summaries_filepath = f"{local_output_prefix}-summaries.csv"
    write_to_csv(summaries, summaries_filepath)
    if bool(bucket_object_prefix):
        print("Writing summaries to S3")
        s3.upload_file(summaries_filepath, OUTPUT_BUCKET_NAME, f"{bucket_object_prefix}-summaries.csv")

    print(f"Running generate todo-list")
    todo_list = generate_todo_list(summaries)

    todo_list_filepath = f"{local_output_prefix}-todo.csv"
    write_to_csv(todo_list, todo_list_filepath)
    if bool(bucket_object_prefix):
        print("Writing todo_list to S3")
        s3.upload_file(todo_list_filepath, OUTPUT_BUCKET_NAME, f"{bucket_object_prefix}-todo.csv")
    return [summaries_filepath, todo_list_filepath]


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
        bucket_object_prefix = f"{sender_name}-{RUN_ID}-{attachment_num}"
        attachment_files = process_file(file_path=file_path, bucket_object_prefix=bucket_object_prefix)
        # TODO: Maybe nicer filenames
        send_response(reply_to_address, attachment_files)
        # TODO: Try to merge summaries and todo_list into one .CSV
        # TODO: Get total token usage as a fun fact (probably need to instantiate a signleton openai class wrapper)


# TODO: Better local testing with running the container locally and curling it with the request (needs S3 I guess).
if __name__ == "__main__":
    attachment_files = process_file("input/kubo.mp4")
    print(f"generated {attachment_files}")
