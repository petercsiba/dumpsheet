import boto3
import email
import os
import subprocess
import time

from botocore.exceptions import NoCredentialsError
from networking_dump import networking_dump

s3 = boto3.client('s3')


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

    # Process the attachments
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

        audio_file = file_path + ".mp4"
        print(f"Running ffmpeg on {file_path} outputting to {audio_file}")
        try:
            subprocess.run(['ffmpeg', '-i', file_path, audio_file], check=True)
            print(f'Converted file saved as: {audio_file}')
        except subprocess.CalledProcessError as e:
            print(f'FFmpeg Error occurred: {e}')

        print(f"Running Sekretar-katka")
        summaries, todo_list = networking_dump(audio_file, file_path)

