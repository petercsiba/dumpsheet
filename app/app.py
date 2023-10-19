# TODO(P0): (De)prioritize all TODOs lol:
# TODO(P0): AWS login credentials should live for at least 8 hours, 1 hour is damn short to have annoying re-login
#   git grep '# TODO' | awk -F: '{print $2 " " $1 " " $3}' | sed -e 's/^[[:space:]]*//' | sort
# TODO(P0, devx): CloudWatch logs are completely useless, slow, cannot search, really only good for developing.

import datetime
import os
import re
import time
import uuid
from typing import List, Optional
from urllib.parse import unquote_plus
from uuid import UUID

import pytz

from app.datashare import PersonDataEntry
from app.emails import (
    send_hubspot_result,
    send_result,
    send_result_no_people_found,
    send_result_rest_of_the_crowd,
    send_technical_failure_email,
)
from app.form import FormData
from app.gsheets import GoogleClient, add_form_data_to_sheet
from app.hubspot_client import HubspotClient
from app.hubspot_dump import HubspotDataEntry, extract_and_sync_contact_with_follow_up
from app.networking_dump import run_executive_assistant_to_get_drafts
from common.aws_utils import get_boto_s3_client, get_bucket_url
from common.config import (
    RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS,
    SKIP_PROCESSED_DATA_ENTRIES,
)
from common.openai_client import OpenAiClient
from common.twillio_client import TwilioClient
from database.account import Account
from database.client import (
    POSTGRES_LOGIN_URL_FROM_ENV,
    connect_to_postgres,
    connect_to_postgres_i_will_call_disconnect_i_promise,
)
from database.constants import DESTINATION_HUBSPOT_ID
from database.data_entry import STATE_UPLOAD_PROCESSED, STATE_UPLOAD_TRANSCRIBED
from database.email_log import EmailLog
from database.models import BaseAccount, BaseDataEntry, BaseOrganization
from database.organization import ORGANIZATION_ROLE_OWNER, Organization
from database.pipeline import Pipeline
from database.task import Task
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


# We use data_entry_id, as the underlying account_id can change in the demo onboarding flow
# Yeah, I know it's kinda junk - we try to track how users come to the platform and merge same emails.
# NOTE: Maximum Lambda run-time is 15 minutes, so waiting longer does not make sense.
def wait_for_email_updated_on_data_entry(
    data_entry_id: UUID, max_wait_seconds: int = 10 * 60
) -> bool:
    start_time = time.time()
    end_time = start_time + max_wait_seconds

    while time.time() < end_time:
        updated_data_entry = BaseDataEntry.get_by_id(data_entry_id)
        account_id = updated_data_entry.account_id
        acc: Account = Account.get_by_id(account_id)
        if acc.get_email() is not None:
            print(f"account {account_id} has email set")

            # TODO(P2, hack): This is the multi-channel onboarding flow account consolidation hack
            if bool(acc.merged_into_id) and account_id != acc.merged_into_id:
                print(
                    f"fixing up data entry to redirect account_id {account_id} to {acc.merged_into_id}"
                )
                updated_data_entry.account_id = acc.merged_into_id
                updated_data_entry.save()

            return True

        # Wait for 10 seconds
        print("waiting for user to input their email address")
        time.sleep(10)

    return False


# TODO(P1, features): Also support this for HubSpot dump.
def sync_people_to_gsheets(account_id: uuid.UUID, form_datas: List[FormData]):
    print(f"Gonna sync {len(form_datas)} FormDatas into GSheets")
    google_client = GoogleClient()
    google_client.login()

    acc: Account = Account.get_by_id(account_id)
    gsheet_id = acc.gsheet_id
    email = acc.get_email()
    if gsheet_id is None:
        if email is None:
            print(
                f"ERROR: Cannot create gsheet for account {account_id} cause no email was found"
            )
            return

        new_spreadsheet = google_client.create(f"Voxana Data Share - {acc.full_name}")
        gsheet_id = new_spreadsheet.id
        google_client.share_with(email)

    google_client.open_by_key(gsheet_id)
    # TODO(P0, UX): We should support multiple spreadsheets by FormDefinition.name - that would need be some refactor.
    sheet = google_client.spreadsheet.get_worksheet(0)
    for form_data in form_datas:
        add_form_data_to_sheet(sheet, form_data)


# Second lambda
def process_transcript_from_data_entry(
    gpt_client: OpenAiClient,
    data_entry: BaseDataEntry,
) -> List[PersonDataEntry]:
    # ===== Actually perform black magic
    # TODO(P1, feature): We should gather general context, e.g. try to infer the event type, the person's vibes, ...
    people_entries = run_executive_assistant_to_get_drafts(
        gpt_client, full_transcript=data_entry.output_transcript
    )

    # wait a bit more
    if not wait_for_email_updated_on_data_entry(data_entry.id, max_wait_seconds=3 * 60):
        raise ValueError(
            f"email missing for data_entry {data_entry.id} - cannot process"
        )
    # This the hack when DataEntry.account_id can be updated, so we re-fetch the stuff.
    data_entry = BaseDataEntry.get_by_id(data_entry.id)

    if len(people_entries) == 0:
        # If this is sent, this should be the only email sent for this data_entry
        send_result_no_people_found(
            account_id=data_entry.account_id,
            idempotency_id_prefix=data_entry.idempotency_id,
            full_transcript=data_entry.output_transcript,
        )
        return people_entries

    rest_of_the_crowd = []
    legit_results = []
    for i, person in enumerate(people_entries):
        if not person.should_show_full_contact_card():
            rest_of_the_crowd.append(person)
            continue

        person.form_data.set_field_value(
            "recording_time", datetime.datetime.now(pytz.UTC)
        )
        legit_results.append(person)

    # UPDATE SPREADSHEET
    # TODO(P1, reliability): Once battle-tested, remove this
    try:
        sync_people_to_gsheets(
            account_id=data_entry.account_id,
            form_datas=[person.form_data for person in legit_results],
        )
    except Exception as ex:
        print(f"ERROR: Cannot sync_people_to_gsheets cause {ex}")

    # SEND EMAILS
    for person in legit_results:
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

    return people_entries


def process_transcript_for_organization(
    hs_client: HubspotClient,
    gpt_client: OpenAiClient,
    data_entry: BaseDataEntry,
) -> HubspotDataEntry:
    acc: Account = Account.get_by_id(data_entry.account_id)
    pipeline = Pipeline.get_or_none_for_org_id(
        acc.organization_id, DESTINATION_HUBSPOT_ID
    )
    hub_id = pipeline.external_org_id if bool(pipeline) else None
    task = Task.create_task(data_entry_id=data_entry.id, pipeline_id=pipeline.id)

    # TODO(P1, ux): Maybe we should wait_for_email_updated_on_data_entry
    #   But then might be better to update without email confirmations.
    data = extract_and_sync_contact_with_follow_up(
        client=hs_client,
        gpt_client=gpt_client,
        db_task=task,
        text=data_entry.output_transcript,
        hub_id=hub_id,
        hubspot_owner_id=acc.organization_user_id,
    )

    # To process and upload the Hubspot entries, we do not need an email address.
    # But to send a confirmation, we do need one.
    if wait_for_email_updated_on_data_entry(data_entry.id, max_wait_seconds=3 * 60):
        send_hubspot_result(data_entry.account, data_entry.idempotency_id, data)
    else:
        print(
            f"WARNING: email missing for data_entry {data_entry.id} - cannot send results email"
        )

    return data


def parse_uuid_from_string(input_string):
    uuid_pattern = re.compile(
        r"[0-9a-f]{8}-"
        r"[0-9a-f]{4}-"
        r"4[0-9a-f]{3}-"
        r"[89ab][0-9a-f]{3}-"
        r"[0-9a-f]{12}",
        re.IGNORECASE,
    )
    match = uuid_pattern.search(input_string)
    if match:
        return UUID(match.group())
    else:
        return None


def first_lambda_handler_wrapper(event, context) -> BaseDataEntry:
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
        # it can include folders, file extensions and such; ideally it should have metadata but unsure with presigned
        data_entry_id = parse_uuid_from_string(key)
        data_entry = process_app_upload(
            gpt_client=gpt_client,
            audio_filepath=download_path,
            data_entry_id=data_entry_id,
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
        # NOTE: KeyError: 'callsid' - likely you re-uploaded the file to this bucket without the metadata.
        call_sid = object_metadata["callsid"]
        phone_number = object_metadata["phonenumber"]
        proper_name = object_metadata["propername"]
        carrier_info = object_metadata.get("carrierinfo")
        print(
            f"Received voicemail from {phone_number}, {proper_name} and {carrier_info}"
        )
        data_entry = process_voice_recording_input(
            gpt_client=gpt_client,
            twilio_client=twilio_client,
            bucket_url=get_bucket_url(bucket, key),
            voice_file_data=s3_get_object_response["Body"].read(),
            call_sid=call_sid,
            phone_number=phone_number,
            full_name=proper_name,
            phone_carrier_info=carrier_info,
            event_timestamp=head_object["LastModified"],
        )
    else:
        raise ValueError(
            f"Un-recognized bucket name {bucket} - please add the mapping in your lambda"
        )

    # If a BaseDataEntry
    data_entry.state = STATE_UPLOAD_TRANSCRIBED
    data_entry.save()

    return data_entry


def second_lambda_handler_wrapper(data_entry: BaseDataEntry):
    if not wait_for_email_updated_on_data_entry(data_entry.id, max_wait_seconds=5 * 60):
        print(
            "WARNING: data entry has no associated email - we might be operating on an incomplete account"
        )
    gpt_client = OpenAiClient()
    acc: BaseAccount = BaseAccount.get_by_id(data_entry.account_id)
    print(f"gonna process transcript for account {acc.__dict__}")
    # TODO(P0, ux): Have a clearer way to decide which path to go with (select box, or "auto-gpt")
    if bool(acc.organization):
        print("Account is part of an organization, will sync data directly there")
        org = Organization.get_by_id(
            acc.organization_id
        )  # acc.organization is of type BaseOrganization
        hs_client = HubspotClient(
            org.get_oauth_data_id_for_destination(DESTINATION_HUBSPOT_ID)
        )
        process_transcript_for_organization(
            hs_client=hs_client,
            gpt_client=gpt_client,
            data_entry=data_entry,
        )
    else:
        # Our OG product
        # NOTE: When we actually separate them - be careful about re-tries to clear the output.
        process_transcript_from_data_entry(
            gpt_client=gpt_client,
            data_entry=data_entry,
        )


def _event_idempotency_id(event):
    # Check if this is an API Gateway Event
    if "requestContext" in event and "requestId" in event["requestContext"]:
        idempotency_key = event["requestContext"]["requestId"]
    # Check if this is an S3 Event
    elif (
        "Records" in event
        and len(event["Records"]) > 0
        and "eventID" in event["Records"][0]
    ):
        idempotency_key = event["Records"][0]["eventID"]
    else:
        idempotency_key = uuid.uuid4()
    return idempotency_key


def lambda_handler(event, context):
    data_entry: Optional[BaseDataEntry] = None
    try:
        data_entry = first_lambda_handler_wrapper(event, context)
    except Exception as err:
        # TODO(P1, ux): Would be nice to notify the user - OR we get really fast into fixing it.
        # -- only possible if we have their email address.
        send_technical_failure_email(err, _event_idempotency_id(event))

    if bool(data_entry):
        data_entry = BaseDataEntry.get_by_id(data_entry.id)
        if (
            SKIP_PROCESSED_DATA_ENTRIES == 1
            and data_entry.state == STATE_UPLOAD_PROCESSED
        ):
            print("INFO: skipping data entry processing cause already processed")
            return

        try:
            second_lambda_handler_wrapper(data_entry)
            data_entry.state = STATE_UPLOAD_PROCESSED
            data_entry.processed_at = datetime.datetime.now()
            data_entry.save()
        except Exception as err:
            send_technical_failure_email(err, str(data_entry.id), data_entry=data_entry)
    else:
        print("INFO: No DataEntry returned by first lambda, skipping second step")


# For local testing without emails or S3, great for bigger refactors.
# TODO(P2): Make this an automated-ish test
#  although would require further mocking of OpenAI calls from the test_.. stuff
if __name__ == "__main__":
    OUTPUT_BUCKET_NAME = None

    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        open_ai_client = OpenAiClient()
        # open_ai_client.run_prompt(f"test {time.time()}")

        test_case = "app"  # FOR EASY TEST CASE SWITCHING
        orig_data_entry = None
        if test_case == "app":
            app_account = Account.get_or_onboard_for_email(
                "test@voxana.ai", utm_source="test"
            )
            app_data_entry_id = BaseDataEntry.insert(
                account=app_account,
                display_name="test_display_name",
                idempotency_id=f"message-id-{time.time()}",
                input_type="app_upload",
            ).execute()
            test_parsing_too = parse_uuid_from_string(
                f"folder/{app_data_entry_id}.webm"
            )
            orig_data_entry = process_app_upload(
                gpt_client=open_ai_client,
                # audio_filepath="testdata/app-silent-audio.webm",
                audio_filepath="testdata/sequioa-guy.webm",
                data_entry_id=test_parsing_too,
            )
        if test_case == "email":
            # with open("testdata/katka-new-draft-test", "rb") as handle:
            with open("testdata/katka-middle-1", "rb") as handle:
                file_contents = handle.read()
                orig_data_entry = process_email_input(
                    gpt_client=open_ai_client,
                    raw_email=file_contents,
                )
        if test_case == "voicemail":
            # Optional
            # test_twilio_client = TwilioClient()
            filepath = "testdata/twilio-mock-recording.wav"
            # In production, we use S3 bucket metadata. Here we just get it from the filename.
            test_full_name = "Peter Csiba"
            test_phone_number = "6502106516"
            test_call_sid = "CAf85701fd23e325761071817c42092922"
            creation_time = datetime.datetime.fromtimestamp(os.path.getctime(filepath))
            with open(filepath, "rb") as handle:
                file_contents = handle.read()
                orig_data_entry = process_voice_recording_input(
                    gpt_client=open_ai_client,
                    # TODO(P1, testing): Support local testing
                    twilio_client=None,
                    bucket_url=None,
                    call_sid=test_call_sid,
                    phone_number=test_phone_number,
                    full_name=test_full_name,
                    phone_carrier_info="T-Mobile consumer stuff",
                    voice_file_data=file_contents,
                    event_timestamp=creation_time,  # reasonably idempotent
                )

        loaded_data_entry = BaseDataEntry.get(BaseDataEntry.id == orig_data_entry.id)
        print(f"loaded_data_entry: {loaded_data_entry}")

        # since we have one TestHubspot integration, all accounts have to be part of the same organization
        # (alternatively we can mock the entire HubspotClient)
        existing_organization: Organization = BaseOrganization.get_or_none(
            BaseOrganization.name == "testing locally"
        )
        if bool(existing_organization):  # Feel free to hardcode by-pass this
            # Make sure the account is connected to this organization
            test_acc: BaseAccount = BaseAccount.get_by_id(orig_data_entry.account_id)
            if (
                test_acc.organization is None
                or test_acc.organization_id != existing_organization.id
            ):
                print("INFO: Linking account to existing organization")
                test_acc.organization_id = existing_organization.id
                test_acc.organization_role = ORGANIZATION_ROLE_OWNER
                test_acc.save()

            test_hs_client = HubspotClient(
                existing_organization.get_oauth_data_id_for_destination(
                    DESTINATION_HUBSPOT_ID
                )
            )
            process_transcript_for_organization(
                hs_client=test_hs_client,
                gpt_client=open_ai_client,
                data_entry=orig_data_entry,
            )
        else:
            # NOTE: We pass "orig_data_entry" here cause the loaded would include the results.
            process_transcript_from_data_entry(
                gpt_client=open_ai_client,
                data_entry=orig_data_entry,
            )

        EmailLog.save_last_email_log_to("result-app-app.html")
