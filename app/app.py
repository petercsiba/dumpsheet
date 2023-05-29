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
RUN_ID = str(datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
SENDER_EMAIL = "assistent@katka.ai"
DEBUG_RECIPIENT = "petherz@gmail.com"


def send_response(email_address, attachment_paths):
    ses = boto3.client('ses')

    sender = SENDER_EMAIL
    recipients = list({email_address, DEBUG_RECIPIENT})
    subject = "Summaries from your last event - please take a look at your todos"
    # TODO: Generate with GPT ideally personalized to the transcript.
    body_text = (
        "Hello, \nSounds you had a blast at your recent event! Good job on meeting all those people "
        "- looking forward to hear more stories from your life!"
    )

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
        print(f'Email sent! Message ID: {response["MessageId"]}')
    except Exception as e:
        print(f'Email failed to send. {e}')


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

    # Process the attachments
    attachment_num = 0
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
        attachment_num += 1
        file_name = f"{time.time()}-{orig_file_name}"
        file_path = os.path.join('/tmp/', file_name)
        with open(file_path, 'wb') as f:
            f.write(part.get_payload(decode=True))

        audio_file = file_path + ".mp4"
        print(f"Running ffmpeg on {file_path} outputting to {audio_file}")
        try:
            subprocess.run(['ffmpeg', '-i', file_path, audio_file], check=True)
            print(f'Converted file saved as: {audio_file}')
        except subprocess.CalledProcessError as e:
            print(f'FFmpeg Error occurred: {e}')

        print(f"Running Sekretar-katka")
        summaries = networking_dump(audio_file)

        # Output storage
        local_output_prefix = file_path
        # Unique identifier to support multiple runs of the same file even if attached multiple times
        bucket_object_prefix = f"{sender_name}-{RUN_ID}-{attachment_num}"
        summaries_filepath = f"{local_output_prefix}-summaries.csv"
        write_to_csv(summaries, summaries_filepath)
        print("Writing summaries to S3")
        s3.upload_file(summaries_filepath, OUTPUT_BUCKET_NAME, f"{bucket_object_prefix}-summaries.csv")

        print(f"Running generate todo-list")
        todo_list = generate_todo_list(summaries)

        todo_list_filepath = f"{local_output_prefix}-todo.csv"
        write_to_csv(todo_list, todo_list_filepath)
        print("Writing todo_list to S3")
        s3.upload_file(todo_list_filepath, OUTPUT_BUCKET_NAME, f"{bucket_object_prefix}-todo.csv")

        send_response(reply_to_address, [summaries_filepath, todo_list_filepath])
        # TODO: Try to merge summaries and todo_list into one .CSV
        # TODO: Get total token usage as a fun fact (probably need to instantiate a signleton openai class wrapper)

