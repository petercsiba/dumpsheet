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
# TODO(P1, devx): Include black, isort, flake (ideally on file save).

import boto3
import copy
import datetime
import email
import re
import subprocess
import traceback

from botocore.exceptions import NoCredentialsError
from dataclasses import asdict
from email.utils import parseaddr
from urllib.parse import quote

from openai_client import OpenAiClient
from dynamodb import setup_dynamodb_local, load_files_to_dynamodb, teardown_dynamodb_local, DynamoDBManager, \
    TABLE_NAME_USER
from aws_utils import get_bucket_url, get_dynamo_endpoint_url
from datashare import DataEntry
from emails import send_confirmation, send_response, store_and_get_attachments_from_email, get_email_params_for_reply
from generate_flashcards import generate_page
from networking_dump import fill_in_draft_outreaches, extract_per_person_summaries, transcribe_audio
from storage_utils import write_output_to_local_and_bucket

OUTPUT_BUCKET_NAME = "katka-emails-response"  # !make sure different from the input!
STATIC_HOSTING_BUCKET_NAME = "katka-ai-static-pages"

s3 = boto3.client('s3')


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


# Second lambda
def process_transcript_from_data_entry(gpt_client, data_entry: DataEntry):
    # ===== Actually perform black magic
    full_name = data_entry.email_reply_params.recipient_full_name
    bucket_object_prefix = f"{full_name}-{data_entry.event_timestamp}"
    bucket_object_prefix = re.sub(r'\s', '-', bucket_object_prefix)
    # Here we merge all successfully processed
    # * audio attachments
    # * email bodies
    # into one giant transcript.
    raw_transcript = "\n\n".join(data_entry.input_transcripts)
    print(f"raw_transcript: {raw_transcript}")

    email_params = copy.deepcopy(data_entry.email_reply_params)
    email_params.attachment_paths = None
    # TODO(P2, devx): Rename project name
    project_name = email_params.recipient_full_name

    # TODO(P3, infra): Use more proper temp fs
    local_output_prefix = f"/tmp/{bucket_object_prefix}"

    # TODO(P0, feature): We should gather general context, e.g. try to infer the event type, the person's vibes, ...
    people_entries = extract_per_person_summaries(gpt_client, raw_transcript=raw_transcript)
    data_entry.output_people_entries = people_entries

    try:
        summaries_filepath, _ = write_output_to_local_and_bucket(
            data=[asdict(pde) for pde in people_entries],
            suffix="-summaries.csv",
            content_type="text/csv",
            local_output_prefix=local_output_prefix,
            bucket_name=OUTPUT_BUCKET_NAME,
            bucket_object_prefix=bucket_object_prefix
        )
    except Exception as err:
        print(f"WARNING: could NOT write summaries to local cause {err}")
        traceback.print_exc()
        summaries_filepath = None

    # This mutates the underlying data_entry.
    fill_in_draft_outreaches(gpt_client, people_entries)

    # TODO(P1, ux): Would be nice to include the full-transcript as a button in the LHS menu
    page_contents = generate_page(
        project_name=project_name,
        event_timestamp=data_entry.event_timestamp,
        person_data_entries=people_entries,
    )
    _, bucket_key = write_output_to_local_and_bucket(
        data=page_contents,
        suffix=".html",
        content_type="text/html",
        local_output_prefix=local_output_prefix,
        bucket_name=STATIC_HOSTING_BUCKET_NAME,
        bucket_object_prefix=bucket_object_prefix
    )
    # TODO(P2, infra): Heard it's better at https://vercel.com/guides/deploying-eleventy-with-vercel
    page_key = quote((bucket_key or "local").encode('utf-8'))
    webpage_url = f"http://{STATIC_HOSTING_BUCKET_NAME}.s3-website-us-west-2.amazonaws.com/{page_key}"
    data_entry.output_webpage_url = webpage_url

    email_params.attachment_paths = [summaries_filepath] if bool(summaries_filepath) else []
    # TODO(P1, peter): Would be nice to pass total tokens used, queries and GPT time.
    send_response(
        email_params=email_params,
        email_datetime=data_entry.event_timestamp,
        webpage_link=webpage_url,
        people_count=len(people_entries),
        drafts_count=sum([len(p.drafts) for p in people_entries]),
        # TODO(P2, reevaluate): Might be better to allow re-generating this.
        idempotency_key=f"{data_entry.event_name}-response"
    )


# First lambda
def process_email_input(dynamodb: DynamoDBManager, raw_email, bucket_url=None) -> DataEntry:
    # TODO(P1, migration): Refactor the email processing to another function which returns some custom object maybe
    print(f"Read raw_email body with {len(raw_email)} bytes")

    # ======== Parse the email
    # TODO(P1): Move this to emails, essentially generate reply-to EmailParams
    msg = email.message_from_bytes(raw_email)
    base_email_params = get_email_params_for_reply(msg)

    # Generate run-id as an idempotency key for re-runs
    if 'Date' in msg:
        email_datetime = email.utils.parsedate_to_datetime(msg['Date'])
    else:
        print(f"email msg does NOT have Date field, defaulting to now for email {base_email_params}")
        email_datetime = datetime.datetime.now()

    attachment_file_paths = store_and_get_attachments_from_email(msg)

    # TODO(P0, migration): Map email address to user_id through DynamoDB
    user = dynamodb.get_or_create_user(email_address=base_email_params.recipient)

    result = DataEntry(
        user_id=user.user_id,
        # IMPORTANT: This is used as idempotency-key all over the place!
        event_name=email_datetime.strftime('%B %d, %H:%M'),
        event_id=msg['Message-ID'],
        event_timestamp=email_datetime,
        email_reply_params=base_email_params,
        input_s3_url=bucket_url,
    )

    try:
        confirmation_email_params = copy.deepcopy(base_email_params)
        confirmation_email_params.attachment_paths = attachment_file_paths
        send_confirmation(params=confirmation_email_params, dedup_prefix=result.event_name)
    except Exception as err:
        print(f"ERROR: Could not send confirmation to {base_email_params.recipient} cause {err}")
        traceback.print_exc()

    for attachment_num, attachment_file_path in enumerate(attachment_file_paths):
        print(f"Processing attachment {attachment_num} out of {len(attachment_file_paths)}")
        audio_filepath = convert_audio_to_mp4(attachment_file_path)
        if bool(audio_filepath):
            result.input_transcripts.append(transcribe_audio(audio_filepath=audio_filepath))

    return result


# TODO(P1, devx): Send email on failure via CloudWatch monitoring (ask GPT how to do it)
#   * ALTERNATIVELY: Can catch exception(s) and send email from here.
#   * BUT we catch some errors.
#   * So maybe we need to migrate to logger?
# TODO(P1, ux, infra): AWS auto-retries lambdas so it is our responsibility to make them idempotent.
def lambda_handler(event, context):
    print(f"Received Event: {event}")
    # Get the bucket name and file key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    bucket_url = get_bucket_url(bucket, key)
    print(f"Bucket URL: {bucket_url}")

    # Download the email from S3
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except NoCredentialsError as e:
        print(f"No creds for S3 cause {e}")
        return 'Execution failed'

    endpoint_url = get_dynamo_endpoint_url()
    try:
        dynamodb_client = DynamoDBManager(endpoint_url=endpoint_url)
    except Exception as err:
        print(f"ERROR: Could NOT create DynamoDB to {endpoint_url} cause {err}")
        dynamodb_client = None

    # TODO(P1, multi-client): For Web/iOS uploads we would un-zip here, decide by bucket name.
    # First Lambda
    data_entry = process_email_input(dynamodb=dynamodb_client, raw_email=response['Body'].read(), bucket_url=bucket_url)
    if bool(dynamodb_client):
        dynamodb_client.write_data_entry(data_entry)

    # Second Lambda
    gpt_client = OpenAiClient(dynamodb=dynamodb_client)
    process_transcript_from_data_entry(gpt_client, data_entry)
    # Update with the outputs
    if bool(dynamodb_client):
        dynamodb_client.write_data_entry(data_entry)


# For local testing without emails or S3, great for bigger refactors.
# TODO(P2): Make this an automated-ish test
#  although would require further mocking of OpenAI calls from the test_.. stuff
if __name__ == "__main__":
    OUTPUT_BUCKET_NAME = None

    process, local_dynamodb = setup_dynamodb_local()
    # For the cases when I mess up development.
    # print(f"Deleting some tables")
    # ddb_client = boto3.client('dynamodb', endpoint_url=get_dynamo_endpoint_url())
    # ddb_client.delete_table(TableName=TABLE_NAME_USER)
    # local_dynamodb.create_user_table_if_not_exists()

    load_files_to_dynamodb(local_dynamodb, "test/fixtures/dynamodb")

    # Maybe all test cases?
    with open("test/test-katka-emails-kimberley", "rb") as handle:
        file_contents = handle.read()
        orig_data_entry = process_email_input(dynamodb=local_dynamodb, raw_email=file_contents)
        local_dynamodb.write_data_entry(orig_data_entry)

        loaded_data_entry = local_dynamodb.read_data_entry(orig_data_entry.user_id, orig_data_entry.event_name)
        print(f"loaded_data_entry: {loaded_data_entry}")

        # DynamoDB is used for caching between local test runs, spares both time and money!
        open_ai_client = OpenAiClient(dynamodb=local_dynamodb)
        process_transcript_from_data_entry(gpt_client=open_ai_client, data_entry=loaded_data_entry)

    teardown_dynamodb_local(process)
