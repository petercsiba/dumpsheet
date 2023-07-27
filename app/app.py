# TODO(P0): (De)prioritize all TODOs lol:
#   git grep '# TODO' | awk -F: '{print $2 " " $1 " " $3}' | sed -e 's/^[[:space:]]*//' | sort

import datetime
import os
import time
from typing import List, Optional
from urllib.parse import unquote_plus

from app.datashare import PersonDataEntry
from app.emails import (
    send_result,
    send_result_no_people_found,
    send_result_rest_of_the_crowd,
)
from app.networking_dump import run_executive_assistant_to_get_drafts
from common.aws_utils import get_boto_s3_client, get_bucket_url
from common.config import RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS
from common.openai_client import OpenAiClient
from common.twillio_client import TwilioClient
from database.account import Account
from database.client import (
    POSTGRES_LOGIN_URL_FROM_ENV,
    connect_to_postgres,
    connect_to_postgres_i_will_call_disconnect_i_promise,
)
from database.models import BaseDataEntry
from input.app_upload import process_app_upload
from input.call import process_voice_recording_input
from input.email import process_email_input

s3 = get_boto_s3_client()


# TODO(P1, devx): Send email on failure via CloudWatch monitoring (ask GPT how to do it)
#   * ALTERNATIVELY: Can catch exception(s) and send email from here.
APP_UPLOADS_BUCKET = "requests-from-api-voxana"
EMAIL_BUCKET = "draft-requests-from-ai-mail-voxana"
PHONE_RECORDINGS_BUCKET = "requests-from-twilio"
# RESPONSE_EMAILS_MAX_PER_DATA_ENTRY = 3


def wait_for_sms_email_update():
    raise NotImplementedError("wait_for_sms_email_update")
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


# Second lambda
def process_transcript_from_data_entry(
    gpt_client: OpenAiClient,
    twilio_client: Optional[TwilioClient],
    data_entry: BaseDataEntry,
) -> List[PersonDataEntry]:
    # ===== Actually perform black magic
    # TODO(P1, feature): We should gather general context, e.g. try to infer the event type, the person's vibes, ...
    people_entries = run_executive_assistant_to_get_drafts(
        gpt_client, full_transcript=data_entry.output_transcript
    )

    rest_of_the_crowd = []
    for i, person in enumerate(people_entries):
        if not person.should_show():
            rest_of_the_crowd.append(person)
            continue
        # if user.contact_method() == "email":
        send_result(
            account_id=data_entry.account_id,
            idempotency_id_prefix=data_entry.idempotency_id,
            person=person,
        )
        time.sleep(RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS)

    if len(rest_of_the_crowd) > 0:
        send_result_rest_of_the_crowd(
            account_id=data_entry.account_id,
            idempotency_id_prefix=data_entry.idempotency_id,
            people=rest_of_the_crowd,
        )

    if len(people_entries) == 0:
        # If this is sent, this should be the only email sent for this data_entry
        send_result_no_people_found(
            account_id=data_entry.account_id,
            idempotency_id_prefix=data_entry.idempotency_id,
            full_transcript=data_entry.output_transcript,
        )

    return people_entries


def lambda_handler(event, context):
    # Get the bucket name and file key from the event
    try:
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
    except Exception as e:
        print("This Lambda currently only supports S3 based events")
        raise e
    print(f"Received Event From Bucket {bucket}")

    # https://stackoverflow.com/questions/37412267/key-given-by-lambda-s3-event-cannot-be-used-when-containing-non-ascii-characters
    key = unquote_plus(event["Records"][0]["s3"]["object"]["key"])

    # Lambda execution context will take care of this promise. We use _ENV instead of secrets manager
    # as was lazy to set up the permissions and code reuse for this lambda.
    print("Initializing globals")
    connect_to_postgres_i_will_call_disconnect_i_promise(POSTGRES_LOGIN_URL_FROM_ENV)
    gpt_client = OpenAiClient()
    twilio_client = TwilioClient()

    # First Lambda
    if bucket == APP_UPLOADS_BUCKET:
        download_path = "/tmp/{}".format(os.path.basename(key))
        s3.download_file(bucket, key, download_path)
        data_entry = process_app_upload(
            gpt_client=gpt_client,
            audio_filepath=download_path,
            data_entry_id_str=key,
        )
    elif bucket == EMAIL_BUCKET:
        raw_email = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        data_entry = process_email_input(
            gpt_client=gpt_client,
            raw_email=raw_email,
            bucket_url=get_bucket_url(bucket, key),
        )
    elif bucket == PHONE_RECORDINGS_BUCKET:
        head_object = s3.head_object(Bucket=bucket, Key=key)
        s3_get_object_response = s3.get_object(Bucket=bucket, Key=key)
        object_metadata = s3_get_object_response["Metadata"]
        # Get the phone number and proper name from the metadata
        # NOTE: the metadata names are case-insensitive, but Amazon S3 returns them in lowercase.
        call_sid = object_metadata["callsid"]
        phone_number = object_metadata["phonenumber"]
        proper_name = object_metadata["propername"]
        data_entry = process_voice_recording_input(
            gpt_client=gpt_client,
            twilio_client=twilio_client,
            bucket_url=get_bucket_url(bucket, key),
            voice_file_data=s3_get_object_response["Body"].read(),
            call_sid=call_sid,
            phone_number=phone_number,
            full_name=proper_name,
            event_timestamp=head_object["LastModified"],
        )
    else:
        raise ValueError(
            f"Un-recognized bucket name {bucket} - please add the mapping in your lambda"
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
        if test_case == "app":
            app_account = Account.get_or_onboard_for_email("test@voxana.ai")
            app_data_entry_id = BaseDataEntry.insert(
                account=app_account,
                display_name="test_display_name",
                idempotency_id=f"message-id-{time.time()}",
                input_type="app_upload",
            ).execute()
            orig_data_entry = process_app_upload(
                gpt_client=open_ai_client,
                audio_filepath="testdata/app-silent-audio.webm",
                data_entry_id_str=str(app_data_entry_id),
            )
        if test_case == "email":
            # with open("testdata/katka-new-draft-test", "rb") as handle:
            with open("testdata/katka-middle-1", "rb") as handle:
                file_contents = handle.read()
                orig_data_entry = process_email_input(
                    gpt_client=open_ai_client,
                    raw_email=file_contents,
                )
        if test_case == "call":
            filepath = "testdata/twilio-mock-recording.wav"
            # In production, we use S3 bucket metadata. Here we just get it from the filename.
            test_full_name = "Peter Csiba"
            test_phone_number = "6502106516"
            call_sid = "CAf85701fd23e325761071817c42092922"
            creation_time = datetime.datetime.fromtimestamp(os.path.getctime(filepath))
            with open(filepath, "rb") as handle:
                file_contents = handle.read()
                orig_data_entry = process_voice_recording_input(
                    gpt_client=open_ai_client,
                    # TODO(P1, testing): Support local testing
                    twilio_client=None,
                    bucket_url=None,
                    call_sid=call_sid,
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
