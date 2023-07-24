# TODO(P0): (De)prioritize all TODOs lol:
#   git grep '# TODO' | awk -F: '{print $2 " " $1 " " $3}' | sed -e 's/^[[:space:]]*//' | sort

import datetime
import os
import re
from typing import List, Optional
from urllib.parse import unquote_plus

from botocore.exceptions import NoCredentialsError

from app.datashare import PersonDataEntry
from app.emails import send_responses
from app.networking_dump import extract_per_person_summaries, fill_in_draft_outreaches
from common.aws_utils import get_boto_s3_client, get_bucket_url
from common.openai_client import OpenAiClient
from common.twillio_client import TwilioClient
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from database.email_log import EmailLog
from database.models import BaseDataEntry
from input.call import process_voice_recording_input
from input.email import process_email_input

s3 = get_boto_s3_client()


# Second lambda
def process_transcript_from_data_entry(
    gpt_client: OpenAiClient,
    twilio_client: Optional[TwilioClient],
    data_entry: BaseDataEntry,
) -> List[PersonDataEntry]:
    # ===== Actually perform black magic
    # TODO(P0, feature): We should gather general context, e.g. try to infer the event type, the person's vibes, ...
    people_entries = extract_per_person_summaries(
        gpt_client, raw_transcript=data_entry.output_transcript
    )
    event_name_safe = re.sub(
        r"\W", "-", data_entry.display_name
    )  # replace all non-alphanum with dashes

    # This mutates the underlying data_entry.
    fill_in_draft_outreaches(gpt_client, people_entries)
    data_entry.save()  # This will only update the fields which have changed.

    # user = User.get_by_id(data_entry.user)
    # if user.contact_method() == "sms":
    #     # TODO(P1, ux): Improve this message, might need an URL shortener
    #     msg = "Your event summary is ready - check your email Inbox"
    #     if not bool(twilio_client):
    #         print(f"SKIPPING send_sms cause no twilio_client would have sent {msg}")
    #     else:
    #         twilio_client.send_sms(to_phone=user.phone, body=msg)
    #         # When onboarding through Voice call & SMS, there is a chance that the email gets updated at a wrong time.
    #         # So lets keep refreshing it a few times to lower the chances.
    #         for i in range(3):
    #             print("Sleeping 1 minute to re-fetch the user - maybe we get the email")
    #             time.sleep(60)
    #             user = User.get_by_id(data_entry.user)
    #             if user.contact_method() == "email":
    #                 print(
    #                     "Great success - email was updated and we can send them a nice confirmation too!"
    #                 )
    #                 break

    # if user.contact_method() == "email":
    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=data_entry.account_id,
        idempotency_id=f"{data_entry.idempotency_id}-response",
        subject=f"The summary from your event at {event_name_safe} is ready for your review!",
    )
    # Removed all_summaries_filepath for now
    email_params.attachment_paths = []
    actions = {}
    for person in people_entries:
        for draft in person.drafts:
            actions[f"{person.name}: {draft.intent}"] = draft.message

    action_names = "\n".join(actions.keys())
    print(f"ALL ACTION SUBJECTS: {action_names}")

    send_responses(
        orig_email_params=email_params,
        actions=actions,
    )

    return people_entries


# TODO(P1, devx): Send email on failure via CloudWatch monitoring (ask GPT how to do it)
#   * ALTERNATIVELY: Can catch exception(s) and send email from here.
EMAIL_BUCKET = "draft-requests-from-ai-mail-voxana"
PHONE_RECORDINGS_BUCKET = "katka-twillio-recordings"  # TODO(migrate)


def lambda_handler(event, context):
    print(f"Received Event: {event}")
    # Get the bucket name and file key from the event
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    # https://stackoverflow.com/questions/37412267/key-given-by-lambda-s3-event-cannot-be-used-when-containing-non-ascii-characters
    key = unquote_plus(event["Records"][0]["s3"]["object"]["key"])
    # Currently only used for tracking purposes
    bucket_url = get_bucket_url(bucket, key)
    print(f"Gonna get S3 object from bucket URL: {bucket_url}")

    # Download the email from S3
    try:
        s3_get_object_response = s3.get_object(Bucket=bucket, Key=key)
    except NoCredentialsError as e:
        print(f"No creds for S3 cause {e}")
        return "Execution failed"
    except Exception as e:
        print(f"Failed to fetch S3 object due to {e}")
        return "Execution failed"
    bucket_raw_data = s3_get_object_response["Body"].read()
    print(f"S3: Fetched object of size {len(bucket_raw_data)}")

    # Setup global deps
    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        gpt_client = OpenAiClient()
        twilio_client = TwilioClient()

        # First Lambda
        if bucket == EMAIL_BUCKET:
            raw_email = bucket_raw_data
            data_entry = process_email_input(
                gpt_client=gpt_client,
                raw_email=raw_email,
                bucket_url=bucket_url,
            )
        elif bucket == PHONE_RECORDINGS_BUCKET:
            voice_file_data = bucket_raw_data
            head_object = s3.head_object(Bucket=bucket, Key=key)
            object_metadata = s3_get_object_response["Metadata"]
            # Get the phone number and proper name from the metadata
            # NOTE: the metadata names are case-insensitive, but Amazon S3 returns them in lowercase.
            call_sid = object_metadata["callsid"]
            phone_number = object_metadata["phonenumber"]
            proper_name = object_metadata["propername"]
            data_entry = process_voice_recording_input(
                gpt_client=gpt_client,
                twilio_client=twilio_client,
                bucket_url=bucket_url,
                voice_file_data=voice_file_data,
                call_sid=call_sid,
                phone_number=phone_number,
                full_name=proper_name,
                event_timestamp=head_object["LastModified"],
            )
        else:
            data_entry = None
            print(
                f"ERROR: Un-recognized bucket name {bucket_url} please add the mapping in your lambda"
            )

        # Second Lambda
        # NOTE: When we actually separate them - be careful about re-tries to clear the output.
        process_transcript_from_data_entry(
            gpt_client=gpt_client,
            twilio_client=twilio_client,
            data_entry=data_entry,
        )


# For local testing without emails or S3, great for bigger refactors.
# TODO(P2): Make this an automated-ish test
#  although would require further mocking of OpenAI calls from the test_.. stuff
if __name__ == "__main__":
    OUTPUT_BUCKET_NAME = None

    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        open_ai_client = OpenAiClient()
        # open_ai_client.run_prompt(f"test {time.time()}")

        test_case = "email"  # FOR EASY TEST CASE SWITCHING
        orig_data_entry = None
        if test_case == "email":
            with open("testdata/email-short-audio", "rb") as handle:
                # with open("test/chris-json-backticks", "rb") as handle:
                file_contents = handle.read()
                # Postgres is used for caching between local test runs, spares both time and money!
                orig_data_entry = process_email_input(
                    gpt_client=open_ai_client,
                    raw_email=file_contents,
                )
        if test_case == "call":
            filename = "6502106516-Peter.Csiba-CA7e063a0e33540dc2496d09f5b81e42aa.wav"
            # In production, we use S3 bucket metadata. Here we just get it from the filename.
            test_full_name = "Peter Csiba"
            test_phone_number = "6502106516"
            filepath = f"test/{filename}"
            creation_time = datetime.datetime.fromtimestamp(os.path.getctime(filepath))
            with open(filepath, "rb") as handle:
                file_contents = handle.read()
                orig_data_entry = process_voice_recording_input(
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

        loaded_data_entry = BaseDataEntry.get(BaseDataEntry.id == orig_data_entry.id)
        print(f"loaded_data_entry: {loaded_data_entry}")

        # NOTE: We pass "orig_data_entry" here cause the loaded would include the results.
        process_transcript_from_data_entry(
            gpt_client=open_ai_client,
            data_entry=orig_data_entry,
            twilio_client=None,
        )
