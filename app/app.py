# TODO(P0): Prioritize all TODOs lol
# TODO(_): General product extension ideas:
#   * Get GPT-4 access
#   * Vertical SaaS (same infra, customizable format), two ways:
#       * guess event type and come up with field summaries.
#       * ideally prompt-engineer per recording type
#   * Merge / update - add knowledge from previous encounters
#   * Event prep - know who will be there
#   * Share networking hacks, like on learning names "use it or lose it", "by association nick from nw", "take notes"
import boto3
import copy
import datetime
import email
import os
import pytz
import re
import subprocess
import time

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr

from emails import get_text_from_email, send_confirmation, send_response, Email
from generate_flashcards import generate_page
from networking_dump import generate_draft_outreaches, extract_per_person_summaries, transcribe_audio
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


def process_transcript(
        email_params: Email,
        raw_transcript,
        email_datetime,
        object_prefix=None,
        network_calls=True
):
    # TODO(P3): Use more proper temp fs
    local_output_prefix = f"/tmp/{object_prefix}"

    # TODO(P0): We should gather general context, e.g. try to infer the event type, the person's vibes, ...
    print(f"Running Sekretar-katka")
    # TODO(P1): Support longer than 3000 word token inputs by some smart chunking.
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
    # TODO(P2): Improve CSV format.
    drafts = generate_draft_outreaches(summaries)
    drafts, _ = write_output_to_local_and_bucket(
        data=drafts,
        suffix="-todo.csv",
        content_type="text/csv",
        local_output_prefix=local_output_prefix,
        bucket_name=OUTPUT_BUCKET_NAME,
        bucket_object_prefix=object_prefix
    )

    print(f"Running generate webpage")
    # TODO(P1): Would be nice to include the full-transcript as a button in the LHS menu
    page_contents = generate_page(email_params, email_datetime, summaries, drafts)
    _, bucket_key = write_output_to_local_and_bucket(
        data=page_contents,
        suffix=".html",
        content_type="text/html",
        local_output_prefix=local_output_prefix,
        bucket_name=STATIC_HOSTING_BUCKET_NAME,
        bucket_object_prefix=object_prefix
    )
    # TODO(P2): Heard it's better at https://vercel.com/guides/deploying-eleventy-with-vercel
    webpage_link = f"http://{STATIC_HOSTING_BUCKET_NAME}.s3-website-us-west-2.amazonaws.com/{bucket_key}"

    email_params.attachment_paths = [summaries_filepath]
    if network_calls:
        # TODO(P0): The general context on people count, event type, summary fields used, your inferred vibes
        #   should be passed back for response email generation.
        send_response(
            email_params=email_params,
            email_datetime=email_datetime,
            webpage_link=webpage_link,
            people_count=len(summaries),
            drafts_count=len(drafts),
        )
    else:
        print(f"Would have sent email to {email_params.recipient} with {webpage_link}")
    # TODO: Get total token usage as a fun fact (probably need to instantiate a singleton openai class wrapper)


def process_email(raw_email, network_calls=True):
    # TODO: Refactor the email processing to another function which returns some custom object maybe
    print(f"Read raw_email body with {len(raw_email)} bytes")

    # Parse the email
    msg = email.message_from_bytes(raw_email)
    from_address = msg.get('From')
    orig_to_address = msg.get('To')
    orig_subject = msg.get('Subject')
    # Parse the address
    sender_name, addr = parseaddr(from_address)
    sender_name = "Person" if sender_name is None else sender_name
    sender_first_name = sender_name.split()[0]
    reply_to_address = msg.get('Reply-To')
    if reply_to_address is None or not isinstance(reply_to_address, str):
        print("No reply-to address provided, falling back to from_address")
        reply_to_address = addr
    print(f"email from {sender_name} ({addr}) reply-to {reply_to_address}")

    # Generate run-id as an idempotency key for re-runs
    if msg['Date']:
        email_datetime = email.utils.parsedate_to_datetime(msg['Date'])
        run_idempotency_key = email_datetime
    else:
        print("Could not find 'Date' header in the email, defaulting to `Message-ID`")
        email_datetime = datetime.datetime.now(pytz.UTC)
        run_idempotency_key = msg['Message-ID']

    base_email_params = Email(
        sender=orig_to_address,
        recipient=sender_name,
        subject=f"Re: {orig_subject}",
        reply_to=[reply_to_address],
    )

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
            # TODO(P0): Only send the email at most once, with retries (blocked by storing stuff).
            confirmation_email_params = copy.deepcopy(base_email_params)
            confirmation_email_params.attachment_paths = attachment_file_paths
            send_confirmation(confirmation_email_params, sender_first_name=sender_first_name)
        else:
            print(f"would have sent confirmation email {base_email_params}")
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

    result_email_params = copy.deepcopy(base_email_params)
    result_email_params.attachment_paths = None
    process_transcript(
        email_params=result_email_params,
        raw_transcript=raw_transcript,
        email_datetime=email_datetime,
        object_prefix=object_prefix,
        network_calls=network_calls,
    )


# TODO(P1): Remove the retry mechanism (leads to two confirmation emails).
# TODO(P1): Send email on failure via CloudWatch monitoring
#     CloudWatch rules respond to system events such as changes to AWS resources.
#     To create a rule that triggers when your Lambda function logs an error message:
#     Go to the CloudWatch service in the AWS Management Console.
#     In the navigation pane, click on "Rules", then "Create rule".
#     For the "Event Source", choose "Event Pattern".
#     Choose "Build event pattern to match events by service".
#     Choose "Service Name" -> "Lambda", "Event Type" -> "AWS API Call via CloudTrail".
#     Then specify the "errorCode" as needed to match error events from your function.
#     For "Targets", choose "SNS topic" and select the SNS topic you created in step 2.
#     Configure input, tags, and permissions as required and create the rule.
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
# TODO(P2): Make this an automated-ish test
#  although would require further mocking of OpenAI calls from the test_.. stuff
if __name__ == "__main__":
    OUTPUT_BUCKET_NAME = None
    # Maybe all test cases?
    with open("test/katka-multimodal", "rb") as handle:
        file_contents = handle.read()
        process_email(file_contents, network_calls=False)
