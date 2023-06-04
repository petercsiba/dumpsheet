# TODO(P0): Prioritize all TODOs lol
# TODO(_): General product extension ideas:
#   * Get GPT-4 access
#   * Vertical SaaS (same infra, customizable format), two ways:
#       * guess event type and come up with field summaries.
#       * ideally prompt-engineer per recording type
#   * Merge / update - add knowledge from previous encounters
#   * Event prep - know who will be there
#   * Share networking hacks, like on learning names "use it or lose it", "by association nick from nw", "take notes"
#   * Self-tact
import traceback

import boto3
import copy
import datetime
import email
import pytz
import re
import subprocess

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr

from emails import get_text_from_email, send_confirmation, send_response, Email, DEBUG_RECIPIENTS, \
    store_and_get_attachments_from_email, get_email_params_for_reply
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
        traceback.print_exc()
        return None
    return audio_file


# TODO(P0, migration): This will become the second lambda, operating on DynamoDB activity events
#   when new DataEntry items are added.
def process_transcript(
        project_name: str,
        raw_transcript: str,
        email_params: Email,
        email_datetime: datetime.datetime,
        object_prefix=None,
        network_calls=True
):
    # TODO(P3, infra): Use more proper temp fs
    local_output_prefix = f"/tmp/{object_prefix}"

    # TODO(P0, feature): We should gather general context, e.g. try to infer the event type, the person's vibes, ...
    print(f"Running Sekretar-katka")
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
    # TODO(P2, feature): Improve CSV format.
    drafts = generate_draft_outreaches(summaries)
    drafts_file_path, _ = write_output_to_local_and_bucket(
        data=drafts,
        suffix="-todo.csv",
        content_type="text/csv",
        local_output_prefix=local_output_prefix,
        bucket_name=OUTPUT_BUCKET_NAME,
        bucket_object_prefix=object_prefix
    )

    print(f"Running generate webpage")
    # TODO(P1, ux): Would be nice to include the full-transcript as a button in the LHS menu
    page_contents = generate_page(
        project_name=project_name,
        email_datetime=email_datetime,
        summaries=summaries,
        drafts=drafts,
    )
    _, bucket_key = write_output_to_local_and_bucket(
        data=page_contents,
        suffix=".html",
        content_type="text/html",
        local_output_prefix=local_output_prefix,
        bucket_name=STATIC_HOSTING_BUCKET_NAME,
        bucket_object_prefix=object_prefix
    )
    # TODO(P2, infra): Heard it's better at https://vercel.com/guides/deploying-eleventy-with-vercel
    webpage_link = f"http://{STATIC_HOSTING_BUCKET_NAME}.s3-website-us-west-2.amazonaws.com/{bucket_key}"

    email_params.attachment_paths = [summaries_filepath]
    if network_calls:
        # TODO(P1, peter): Would be nice to pass total tokens used, queries and GPT time.
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
    # TODO(P1, migration): Refactor the email processing to another function which returns some custom object maybe
    print(f"Read raw_email body with {len(raw_email)} bytes, network_calls={network_calls}")

    # ======== Parse the email
    # TODO(P1): Move this to emails, essentially generate reply-to EmailParams
    msg = email.message_from_bytes(raw_email)
    base_email_params = get_email_params_for_reply(msg)

    # Generate run-id as an idempotency key for re-runs
    if msg['Date']:
        email_datetime = email.utils.parsedate_to_datetime(msg['Date'])
        run_idempotency_key = email_datetime
    else:
        print("Could not find 'Date' header in the email, defaulting to `Message-ID`")
        email_datetime = datetime.datetime.now(pytz.UTC)
        run_idempotency_key = msg['Message-ID']

    attachment_file_paths = store_and_get_attachments_from_email(msg)

    try:
        if network_calls:
            # TODO(P0): Only send the email at most once, with retries (blocked by storing stuff).
            confirmation_email_params = copy.deepcopy(base_email_params)
            confirmation_email_params.attachment_paths = attachment_file_paths
            send_confirmation(params=confirmation_email_params)
        else:
            print(f"would have sent confirmation email {base_email_params}")
    except Exception as err:
        print(f"ERROR: Could not send confirmation to {base_email_params.recipient} cause {err}")
        traceback.print_exc()

    # ===== Actually perform black magic
    raw_transcripts = []
    for attachment_num, attachment_file_path in enumerate(attachment_file_paths):
        print(f"Processing attachment {attachment_num} out of {len(attachment_file_paths)}")
        audio_filepath = convert_audio_to_mp4(attachment_file_path)
        if bool(audio_filepath):
            raw_transcripts.append(transcribe_audio(audio_filepath=audio_filepath))

    object_prefix = f"{base_email_params.recipient_full_name}-{run_idempotency_key}"
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
        project_name=result_email_params.recipient_full_name,
        raw_transcript=raw_transcript,
        email_params=result_email_params,
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
        print(f"No creds for S3 cause {e}")
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
