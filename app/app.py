import os
import json

import os
import boto3
import email
import base64
from botocore.exceptions import NoCredentialsError

s3 = boto3.client('s3')

# Parse the email
msg = email.message_from_bytes(raw_email)


def write_to_tmpfs(filename, content):
    with open(f'/dev/shm/{filename}', 'w') as file:
        file.write(content)


def get_attachment_from_email(raw_email):
    # Process the attachments
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        # Get the attachment's filename
        fileName = part.get_filename()

        if bool(fileName):
            # If there is an attachment, save it to a file
            filePath = os.path.join('/tmp/', fileName)
            if not os.path.isfile(filePath):
                with open(filePath, 'wb') as f:
                    f.write(part.get_payload(decode=True))


def lambda_handler(event, context):
    # Get the bucket name and file key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    # Download the email from S3
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except NoCredentialsError as e:
        print(e)
        return 'Execution failed'

    raw_email = response['Body'].read()

    return 'Execution succeeded'
