# TODO(P0): Prioritize all TODOs lol:
#   git grep '# TODO' | awk -F: '{print $2 " " $1 " " $3}' | sed -e 's/^[[:space:]]*//' | sort
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
# TODO(P0, research): Explore Algolia or other enterprise search tools before going to implement ours
#   * https://www.algolia.com/doc/guides/sending-and-managing-data/prepare-your-data/
#   * https://www.wsj.com/articles/businesses-seek-out-chatgpt-tech-for-searching-and-analyzing-their-own-data-393ef4fb
#   * Plugins seem to specialize into search, either PDFs or web: https://chat.openai.com/?model=gpt-4-plugins
# TODO(P0, research): Try using Meta's VoiceBox to be more like a voice-first assistant:
#   * http://ai.facebook.com/blog/voicebox-generative-ai-model-speech?trk=public_post_comment-text

import boto3
import copy
import datetime
import email
import re
import subprocess
import traceback

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr
from urllib.parse import quote

from openai_client import OpenAiClient
from dynamodb import setup_dynamodb_local, teardown_dynamodb_local, DynamoDBManager
from aws_utils import get_bucket_url, get_dynamo_endpoint_url
from datashare import DataEntry
from emails import send_confirmation, send_response, store_and_get_attachments_from_email, get_email_params_for_reply
from generate_flashcards import generate_page
from networking_dump import fill_in_draft_outreaches, extract_per_person_summaries
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


def dump_page(page_contents, local_output_prefix, bucket_object_prefix):
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
    return f"http://{STATIC_HOSTING_BUCKET_NAME}.s3-website-us-west-2.amazonaws.com/{page_key}"


# Second lambda
def process_transcript_from_data_entry(dynamodb: DynamoDBManager, gpt_client: OpenAiClient, data_entry: DataEntry):
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
    dynamodb.write_data_entry(data_entry)  # Only update would be nice

    try:
        summaries_filepath, _ = write_output_to_local_and_bucket(
            # TODO(P0, ux): Generate .XLS
            data=[pde.to_csv_map() for pde in people_entries],
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
    dynamodb.write_data_entry(data_entry)  # Only update would be nice

    # TODO(P1, ux): Would be nice to include the original full-transcript on the event page.
    # === Generate page with only the new events
    event_page_contents = generate_page(
        project_name=f"{project_name} - Event",
        event_timestamp=data_entry.event_timestamp,
        person_data_entries=people_entries,
    )
    data_entry.output_webpage_url = dump_page(event_page_contents, local_output_prefix, bucket_object_prefix)

    # === Generate page for all people of this user
    user = dynamodb.get_or_create_user(email_address=email_params.recipient)
    all_data_entries = dynamodb.get_all_data_entries_for_user(user_id=user.user_id)
    list_of_lists = [de.output_people_entries for de in all_data_entries]
    all_people_entries = [item for sublist in list_of_lists for item in sublist]  # GPT generated no idea how it works
    print(f"all_people_entries {all_people_entries}")
    all_people_entries = sorted(all_people_entries, key=lambda pde: pde.sort_key())

    # TODO(P1, devx): This is logically the same as the above just with all_people_entries so abstract to sth.
    try:
        all_summaries_filepath, _ = write_output_to_local_and_bucket(
            data=[pde.to_csv_map() for pde in all_people_entries],
            suffix="-summaries-all.csv",
            content_type="text/csv",
            local_output_prefix=local_output_prefix,
            bucket_name=OUTPUT_BUCKET_NAME,
            bucket_object_prefix=bucket_object_prefix
        )
    except Exception as err:
        print(f"WARNING: could NOT write summaries ALL to local cause {err}")
        traceback.print_exc()
        all_summaries_filepath = None
    all_page_contents = generate_page(
        project_name=f"{project_name} - All",
        event_timestamp=datetime.datetime.now(),
        person_data_entries=all_people_entries,
    )
    data_entry.all_webpage_url = dump_page(
        all_page_contents,
        local_output_prefix=f"{local_output_prefix}-all",
        bucket_object_prefix=user.main_page_name()
    )
    if bool(dynamodb):
        print(f"Updating all_webpage_url for {data_entry.user_id} after generate all page")
        dynamodb.write_data_entry(data_entry)

    email_params.attachment_paths = [x for x in [summaries_filepath, all_summaries_filepath] if x is not None]
    send_response(
        email_params=email_params,
        email_datetime=data_entry.event_timestamp,
        webpage_link=data_entry.output_webpage_url,
        all_webpage_url=data_entry.all_webpage_url,
        people_count=len(people_entries),
        drafts_count=sum([len(p.drafts) for p in people_entries]),
        prompt_stats=gpt_client.sum_up_prompt_stats(),
        # TODO(P2, reevaluate): Might be better to allow re-generating this.
        idempotency_key=f"{data_entry.event_name}-response"
    )


# First lambda
def process_email_input(dynamodb: DynamoDBManager, gpt_client: OpenAiClient, raw_email, bucket_url=None) -> DataEntry:
    # TODO(P1, migration): Refactor the email processing to another function which returns some custom object maybe
    print(f"Read raw_email body with {len(raw_email)} bytes")

    # ======== Parse the email
    msg = email.message_from_bytes(raw_email)
    base_email_params = get_email_params_for_reply(msg)

    # Generate run-id as an idempotency key for re-runs
    if 'Date' in msg:
        email_datetime = email.utils.parsedate_to_datetime(msg['Date'])
    else:
        print(f"email msg does NOT have Date field, defaulting to now for email {base_email_params}")
        email_datetime = datetime.datetime.now()

    attachment_file_paths = store_and_get_attachments_from_email(msg)

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
        # NOTE: We do NOT include the original attachments cause
        # botocore.exceptions.ClientError: An error occurred (InvalidParameterValue)
        # when calling the SendRawEmail operation: Message length is more than 10485760 bytes long: '24081986'.
        # confirmation_email_params.attachment_paths = attachment_file_paths
        send_confirmation(
            params=confirmation_email_params,
            attachment_paths=attachment_file_paths,
            dedup_prefix=result.event_name
        )
    except Exception as err:
        print(f"ERROR: Could not send confirmation to {base_email_params.recipient} cause {err}")
        traceback.print_exc()

    for attachment_num, attachment_file_path in enumerate(attachment_file_paths):
        print(f"Processing attachment {attachment_num} out of {len(attachment_file_paths)}")
        audio_filepath = convert_audio_to_mp4(attachment_file_path)
        if bool(audio_filepath):
            result.input_transcripts.append(gpt_client.transcribe_audio(audio_filepath=audio_filepath))

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
    gpt_client = OpenAiClient(dynamodb=dynamodb_client)
    raw_email = response['Body'].read()
    data_entry = process_email_input(
        dynamodb=dynamodb_client,
        gpt_client=gpt_client,
        raw_email=raw_email,
        bucket_url=bucket_url
    )
    if bool(dynamodb_client):
        dynamodb_client.write_data_entry(data_entry)

    # Second Lambda
    # NOTE: When we actually separate them - be careful about re-tries to clear the output.
    process_transcript_from_data_entry(dynamodb=dynamodb_client, gpt_client=gpt_client, data_entry=data_entry)


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

    with open("test/test-katka-emails-kimberley", "rb") as handle:
        file_contents = handle.read()
        # DynamoDB is used for caching between local test runs, spares both time and money!
        open_ai_client = OpenAiClient(dynamodb=local_dynamodb)
        orig_data_entry = process_email_input(dynamodb=local_dynamodb, gpt_client=open_ai_client, raw_email=file_contents)
        local_dynamodb.write_data_entry(orig_data_entry)

        loaded_data_entry = local_dynamodb.read_data_entry(orig_data_entry.user_id, orig_data_entry.event_name)
        print(f"loaded_data_entry: {loaded_data_entry}")

        # NOTE: We pass "orig_data_entry" here cause the loaded would include the results.
        process_transcript_from_data_entry(
            dynamodb=local_dynamodb,
            gpt_client=open_ai_client,
            data_entry=orig_data_entry
        )

    teardown_dynamodb_local(process)
