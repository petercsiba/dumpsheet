# TODO(P0): PLAN MIGRATION TO VOXANA; Will just wing-it.
#  * Add basic double-write for katka and peter (today)
#    * For now just users and todos
#  * Create a new branch (wednesday all day)
#  * Strip the functionality:
#    * NO HTML GEN
#    * NO DYNAMO DB
#    *   Figure out caching and idempotency.
#    *   (P1, devx): Figure out some lightweight ORM?
#    *     * SQLAlchemy can generate schemas out of describe, so we can supabase pull, apply, generate on-commit hook.
#  * Move transactional emails to HubSpot (see my Notes)
#  * Eventually migrate old data (TBD on triggers)
#
# TODO(P0): Prioritize all TODOs lol:
#   git grep '# TODO' | awk -F: '{print $2 " " $1 " " $3}' | sed -e 's/^[[:space:]]*//' | sort
# TODO(_): General product extension ideas:
#   * Custom Fields configuration
#   * Vertical SaaS (same infra, customizable format), two ways:
#       * guess event type and come up with field summaries.
#       * ideally prompt-engineer per recording type
#   * Merge / update - add knowledge from previous encounters
#   * Event prep - know who will be there
#   * Share networking hacks, like on learning names "use it or lose it", "by association nick from nw", "take notes"
#   * Self-tact
# TODO(P1, devx): Include black, isort, flake (ideally on file save).
# TODO(P2, research): Explore Algolia or other enterprise search tools before going to implement ours
#   * https://www.algolia.com/doc/guides/sending-and-managing-data/prepare-your-data/
#   * https://www.wsj.com/articles/businesses-seek-out-chatgpt-tech-for-searching-and-analyzing-their-own-data-393ef4fb
#   * Plugins seem to specialize into search, either PDFs or web: https://chat.openai.com/?model=gpt-4-plugins
# TODO(P0, research): Try using Meta's VoiceBox to be more like a voice-first assistant:
#   * http://ai.facebook.com/blog/voicebox-generative-ai-model-speech?trk=public_post_comment-text
# TODO(P1, devx): Start integrating tools like:
#   * Github actions
#   * Doppler
#   * Better stack
#   * https://distoai.com/
# TODO(P0, ux): For not-found websites have a nicer error.html (or rederict) in
#   * https://s3.console.aws.amazon.com/s3/bucket/static.katka.ai/property/website/edit?region=us-west-2
import time

import boto3
import copy
import datetime
import email
import os
import re
import subprocess
import traceback

from botocore.exceptions import NoCredentialsError
from email.utils import parseaddr
from urllib.parse import unquote_plus
from typing import Optional

from supabase_client import get_postgres_connection, get_magic_link_and_create_user_if_does_not_exists, \
    get_user_id_for_email, insert_into_todos, supabase
from openai_client import OpenAiClient
from dynamodb import setup_dynamodb_local, teardown_dynamodb_local, DynamoDBManager, TABLE_NAME_USER
from aws_utils import get_bucket_url, get_dynamo_endpoint_url, get_boto_s3_client
from datashare import DataEntry
from emails import send_confirmation, send_responses, store_and_get_attachments_from_email, get_email_params_for_reply
from networking_dump import fill_in_draft_outreaches, extract_per_person_summaries
from storage_utils import pretty_filesize_int
from test_utils import extract_phone_number_from_filename
from twillio_client import TwilioClient

s3 = get_boto_s3_client()


def do_voxana(dynamodb: DynamoDBManager, data_entry: DataEntry):
    # Later for migration all_data_entries = dynamodb.get_all_data_entries_for_user(user_id=user.user_id)
    print(f"DO VOXANA for {data_entry.user_id}")

    with get_postgres_connection() as postgres_conn:
        dynamodb_user = dynamodb.get_user(user_id=data_entry.user_id)
        email = dynamodb_user.email_address
        # TODO(ux, P1): Reconstruct this magic link
        get_magic_link_and_create_user_if_does_not_exists(email=email)
        supabase_user_id = get_user_id_for_email(postgres_conn, email)
        print(f"gonna insert todos for {len(data_entry.output_people_entries)} people for user {supabase_user_id}")

        todos = []
        for pde in data_entry.output_people_entries:
            for draft in pde.follow_ups:
                todos.append({
                    "user_id": supabase_user_id,
                    "task": f"{pde.name} ({pde.priority} from {data_entry.event_timestamp}): {draft}",
                    "is_complete": False,
                })
        insert_into_todos(postgres_conn, todos)

        # Just try querying:
        response = supabase.table('todos').select("*").execute()
        print(f"all todos for user {supabase_user_id}: {response}")

        supabase.auth.sign_out()


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
def process_transcript_from_data_entry(
        dynamodb: DynamoDBManager,
        gpt_client: OpenAiClient,
        twilio_client: Optional[TwilioClient],
        data_entry: DataEntry
):
    # ===== Actually perform black magic
    # Here we merge all successfully processed
    # * audio attachments
    # * email bodies
    # into one giant transcript.
    raw_transcript = "\n\n".join(data_entry.input_transcripts)
    print(f"raw_transcript: {raw_transcript}")

    # TODO(P0, feature): We should gather general context, e.g. try to infer the event type, the person's vibes, ...
    people_entries = extract_per_person_summaries(gpt_client, raw_transcript=raw_transcript)
    data_entry.output_people_entries = people_entries
    # TODO(P0, edge-cases): Make it work with 0 people
    dynamodb.write_data_entry(data_entry)  # Only update would be nice
    event_name_safe = re.sub(r'\W', '-', data_entry.event_name)  # replace all non-alphanum with dashes

    # This mutates the underlying data_entry.
    fill_in_draft_outreaches(gpt_client, people_entries)
    dynamodb.write_data_entry(data_entry)  # Only update would be nice

    user = dynamodb.get_user(user_id=data_entry.user_id)
    if user.email_address in ["petherz@gmail.com", "kata.sabo@gmail.com"]:
        try:
            do_voxana(dynamodb, data_entry)
        except Exception as ex:
            print(f"do voxana failed with (we gonna carry on): {ex}")
            traceback.print_exc()

    if user.contact_method() == "sms":
        # TODO(P1, ux): Improve this message, might need an URL shortener
        msg = f"Your event summary is ready - check your email Inbox"
        if not bool(twilio_client):
            print(f"SKIPPING send_sms cause no twilio_client would have sent {msg}")
        else:
            twilio_client.send_sms(
                to_phone=user.phone_number,
                body=msg
            )
            # When onboarding through Voice call & SMS, there is a chance that the email gets updated at a wrong time.
            # So lets keep refreshing it a few times to lower the chances.
            for i in range(3):
                print("Sleeping 1 minute to re-fetch the user - maybe we get the email")
                time.sleep(60)
                user = dynamodb.get_user(user.user_id)
                if user.contact_method() == "email":
                    print("Great success - email was updated and we can send them a nice confirmation too!")
                    break

    if user.contact_method() == "email":
        email_params = user.get_email_reply_params(
            subject=f"The summary from your event at {event_name_safe} is ready for your review!"
        )
        # Removed all_summaries_filepath for now
        email_params.attachment_paths = []
        actions = {}
        for person in people_entries:
            for draft in person.drafts:
                actions[f"{person.name}: {draft.intent}"] = draft.message

        action_names = '\n'.join(actions.keys())
        print(f"ALL ACTION SUBJECTS: {action_names}")

        send_responses(
            event_name=event_name_safe,
            email_params=email_params,
            actions=actions,
            idempotency_key_prefix=f"{data_entry.event_name}-response"
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

    user = dynamodb.get_or_create_user(
        email_address=base_email_params.recipient,
        phone_number=None,
        full_name=base_email_params.recipient_full_name
    )

    result = DataEntry(
        user_id=user.user_id,
        # IMPORTANT: This is used as idempotency-key all over the place!
        event_name=email_datetime.strftime('%B %d, %H:%M'),
        event_id=msg['Message-ID'],
        event_timestamp=email_datetime,
        input_type="email",
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


def process_voice_recording_input(
        dynamodb: DynamoDBManager,
        gpt_client: OpenAiClient,
        twilio_client: Optional[TwilioClient],
        bucket_url: Optional[str],  # for tracking purposes
        call_sid: str,
        voice_file_data: bytes,
        phone_number: str,
        full_name: str,
        event_timestamp: datetime.datetime,
) -> Optional[DataEntry]:
    print(f"Read {bucket_url} voice_file_data with {len(voice_file_data)} bytes")

    msg = (
        f"I have received your voicemail (size {pretty_filesize_int(len(voice_file_data))}). "
        "To get your results, please respond with a text contain your email address. "
        "To opt-out, please respond with 'NO'. Thank you!"
    )
    if bool(twilio_client):
        twilio_client.send_sms(
            phone_number,
            body=msg,
        )
    else:
        print(f"SKIPPING send_sms cause no twilio_client would have sent {msg}")

    user = dynamodb.get_or_create_user(email_address=None, phone_number=phone_number, full_name=full_name)
    result = DataEntry(
        user_id=user.user_id,
        # IMPORTANT: This is used as idempotency-key all over the place!
        event_name=event_timestamp.strftime('%B %d, %H:%M'),
        event_id=call_sid,
        event_timestamp=event_timestamp,
        input_type="phone",
        input_s3_url=bucket_url,
    )

    file_path = os.path.join('/tmp/', call_sid)
    with open(file_path, 'wb') as f:
        f.write(voice_file_data)
    audio_filepath = convert_audio_to_mp4(file_path)
    if bool(audio_filepath):
        result.input_transcripts.append(gpt_client.transcribe_audio(audio_filepath=audio_filepath))

    return result


# TODO(P1, devx): Send email on failure via CloudWatch monitoring (ask GPT how to do it)
#   * ALTERNATIVELY: Can catch exception(s) and send email from here.
#   * BUT we catch some errors.
#   * So maybe we need to migrate to logger?
# TODO(P1, ux, infra): AWS auto-retries lambdas so it is our responsibility to make them idempotent.
EMAIL_BUCKET = "katka-emails"
PHONE_RECORDINGS_BUCKET = "katka-twillio-recordings"


def lambda_handler(event, context):
    print(f"Received Event: {event}")
    # Get the bucket name and file key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    # https://stackoverflow.com/questions/37412267/key-given-by-lambda-s3-event-cannot-be-used-when-containing-non-ascii-characters
    key = unquote_plus(event['Records'][0]['s3']['object']['key'])
    # Currently only used for tracking purposes
    bucket_url = get_bucket_url(bucket, key)
    print(f"Gonna get S3 object from bucket URL: {bucket_url}")

    # Download the email from S3
    try:
        s3_get_object_response = s3.get_object(Bucket=bucket, Key=key)
    except NoCredentialsError as e:
        print(f"No creds for S3 cause {e}")
        return 'Execution failed'
    except Exception as e:
        print(f"Failed to fetch S3 object due to {e}")
        return 'Execution failed'
    bucket_raw_data = s3_get_object_response['Body'].read()
    print(f"S3: Fetched object of size {len(bucket_raw_data)}")

    # Setup global deps
    endpoint_url = get_dynamo_endpoint_url()
    try:
        dynamodb_client = DynamoDBManager(endpoint_url=endpoint_url)
    except Exception as err:
        print(f"ERROR: Could NOT connect DynamoDB to {endpoint_url} cause {err}")
        # TODO(p3, devx): Make this a fatal error
        dynamodb_client = None

    gpt_client = OpenAiClient(dynamodb=dynamodb_client)
    twilio_client = TwilioClient()

    # First Lambda
    if bucket == EMAIL_BUCKET:
        raw_email = bucket_raw_data
        data_entry = process_email_input(
            dynamodb=dynamodb_client,
            gpt_client=gpt_client,
            raw_email=raw_email,
            bucket_url=bucket_url
        )
    elif bucket == PHONE_RECORDINGS_BUCKET:
        voice_file_data = bucket_raw_data
        head_object = s3.head_object(Bucket=bucket, Key=key)
        object_metadata = s3_get_object_response['Metadata']
        # Get the phone number and proper name from the metadata
        # NOTE: the metadata names are case-insensitive, but Amazon S3 returns them in lowercase.
        call_sid = object_metadata['callsid']
        phone_number = object_metadata['phonenumber']
        proper_name = object_metadata['propername']
        data_entry = process_voice_recording_input(
            dynamodb=dynamodb_client,
            gpt_client=gpt_client,
            twilio_client=twilio_client,
            bucket_url=bucket_url,
            voice_file_data=voice_file_data,
            call_sid=call_sid,
            phone_number=phone_number,
            full_name=proper_name,
            event_timestamp=head_object['LastModified']
        )
    else:
        data_entry = None
        print(f"ERROR: Un-recognized bucket name {bucket_url} please add the mapping in your lambda")
    if bool(dynamodb_client):
        dynamodb_client.write_data_entry(data_entry)

    # Second Lambda
    # NOTE: When we actually separate them - be careful about re-tries to clear the output.
    process_transcript_from_data_entry(
        dynamodb=dynamodb_client,
        gpt_client=gpt_client,
        twilio_client=twilio_client,
        data_entry=data_entry
    )


# For local testing without emails or S3, great for bigger refactors.
# TODO(P2): Make this an automated-ish test
#  although would require further mocking of OpenAI calls from the test_.. stuff
if __name__ == "__main__":
    OUTPUT_BUCKET_NAME = None

    process, local_dynamodb = setup_dynamodb_local()
    # DynamoDB is used for caching between local test runs, spares both time and money!
    open_ai_client = OpenAiClient(dynamodb=local_dynamodb)
    # For the cases when I mess up development.
    # print(f"Deleting some tables")
    ddb_client = boto3.client('dynamodb', endpoint_url=get_dynamo_endpoint_url())
    ddb_client.delete_table(TableName=TABLE_NAME_USER)
    local_dynamodb.create_user_table_if_not_exists()

    test_case = "email"  # FOR EASY TEST CASE SWITCHING
    orig_data_entry = None
    if test_case == "email":
        with open("test/katka-cbs-action", "rb") as handle:
        # with open("test/chris-json-backticks", "rb") as handle:
            file_contents = handle.read()
            # DynamoDB is used for caching between local test runs, spares both time and money!
            open_ai_client = OpenAiClient(dynamodb=local_dynamodb)
            orig_data_entry = process_email_input(
                dynamodb=local_dynamodb,
                gpt_client=open_ai_client,
                raw_email=file_contents
            )
            local_dynamodb.write_data_entry(orig_data_entry)
    if test_case == "call":
        filename = "6502106516-Peter.Csiba-CA7e063a0e33540dc2496d09f5b81e42aa.wav"
        # In production, we use S3 bucket metadata. Here we just get it from the filename.
        test_phone_number, test_full_name = extract_phone_number_from_filename(filename)
        filepath = f"test/{filename}"
        creation_time = datetime.datetime.fromtimestamp(os.path.getctime(filepath))
        with open(filepath, "rb") as handle:
            file_contents = handle.read()
            orig_data_entry = process_voice_recording_input(
                dynamodb=local_dynamodb,
                gpt_client=open_ai_client,
                # TODO(P1, testing): Support local testing
                twilio_client=None,
                bucket_url=None,
                call_sid=str(creation_time),
                phone_number=test_phone_number,
                full_name=test_full_name,
                voice_file_data=file_contents,
                event_timestamp=creation_time,  # reasonably idempotent
            )
            local_dynamodb.write_data_entry(orig_data_entry)

    loaded_data_entry = local_dynamodb.read_data_entry(orig_data_entry.user_id, orig_data_entry.event_name)
    print(f"loaded_data_entry: {loaded_data_entry}")

    # NOTE: We pass "orig_data_entry" here cause the loaded would include the results.
    process_transcript_from_data_entry(
        dynamodb=local_dynamodb,
        gpt_client=open_ai_client,
        data_entry=orig_data_entry,
        twilio_client=None,
    )

    teardown_dynamodb_local(process)
