# TODO(P0): (De)prioritize all TODOs lol

import datetime
import os
import re
import time
import traceback
import uuid
from typing import List, Optional
from urllib.parse import unquote_plus
from uuid import UUID

from app.contacts_dump import run_executive_assistant_to_get_drafts
from app.datashare import PersonDataEntry
from app.emails import (
    send_networking_per_person_result,
    send_result_no_people_found,
    send_result_rest_of_the_crowd,
    send_technical_failure_email,
    wait_for_email_updated_on_data_entry, send_generic_result,
)
from app.food_dump import run_food_ingredient_extraction
from app.form_library import FormName
from app.gsheets import TEMPLATE_CONTACTS_SPREADSHEET_ID, GoogleClient
from common.aws_utils import get_boto_s3_client, get_bucket_url
from common.config import (
    RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS,
    SKIP_PROCESSED_DATA_ENTRIES,
    SKIP_SHARE_SPREADSHEET, POSTGRES_LOGIN_URL_FROM_ENV,
)
from gpt_form_filler.form import FormData
from gpt_form_filler.openai_client import CHEAPEST_MODEL, OpenAiClient, BEST_MODEL

from common.gpt_client import open_ai_client_with_db_cache
from common.twillio_client import TwilioClient
from database.account import Account
from supawee.client import (
    connect_to_postgres,
    connect_to_postgres_i_will_call_disconnect_i_promise,
)
from database.data_entry import STATE_UPLOAD_PROCESSED, STATE_UPLOAD_TRANSCRIBED
from database.email_log import EmailLog
from database.models import BaseAccount, BaseDataEntry
from database.task import Task
from input.app_upload import process_app_upload
from input.call import process_voice_recording_input
from input.email import process_email_input

s3 = get_boto_s3_client()


APP_UPLOADS_BUCKET = "requests-from-api-voxana"
EMAIL_BUCKET = "draft-requests-from-ai-mail-voxana"
PHONE_RECORDINGS_BUCKET = "requests-from-twilio"
GPTo_MODEL = "gpt-4o-2024-08-06"
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


def sync_form_datas_to_gsheets(account_id: uuid.UUID, form_datas: List[FormData]):
    print(
        f"Gonna sync {len(form_datas)} FormDatas into GSheets for account {account_id}"
    )
    google_client = GoogleClient()
    google_client.login()

    acc: Account = Account.get_by_id(account_id)
    if acc.gsheet_id is None:
        name = acc.full_name
        if name is None:
            name = acc.get_email()
        name_suffix = f" - {name}" if bool(name) else ""

        new_spreadsheet = google_client.copy_from(
            TEMPLATE_CONTACTS_SPREADSHEET_ID,
            new_name=f"Voxana Records For{name_suffix}",
        )
        gsheet_id = new_spreadsheet.id
        acc.gsheet_id = gsheet_id
        acc.save()
        print(f"gsheet attached {gsheet_id} to account {acc.id}")

        if SKIP_SHARE_SPREADSHEET == "1":
            print("INFO: Skip sharing new spreadsheet cause SKIP_SHARE_SPREADSHEET")
            return

        # TODO(P1, reliability): If not yet shared, then always share with the account email.
        google_client.share_with(acc)

    google_client.open_by_key(acc.gsheet_id)

    # TODO(P0, ux): Remove last row from the template when it's created - we can add a hidden DELETE ME somewhere.
    google_client.add_form_datas_to_spreadsheet(form_datas)


# Second lambda
FORM_CLASSIFICATION = {
    FormName.CONTACTS.value: "a voice note on a conversation i had with one or multiple people",
    FormName.FOOD_LOG.value: "foods or ingredient i ate",
}


# TODO(P1, dumpsheet migration): This is trying to be over-smart, we should just have the user to choose the sheet.
def get_workflow_name(gpt_client: OpenAiClient, transcript: str) -> Optional[FormName]:
    # # TODO: While Katka wants it
    print("get_workflow_name just hardcoded to return contacts")
    return FormName.CONTACTS

    # query = """
    # For the below transcript, check if it talks about any of these topics. Output the topic name or None if none fit.
    # The topics are structured as a python dictionary keyed name and value is description.
    # Only output one of the dictionary keys, or return None if none of them fit very well.
    # Topics: {topics}
    # Transcript: {transcript}
    # """.format(
    #     topics=FORM_CLASSIFICATION,
    #     transcript=transcript,
    # )
    # raw_response = gpt_client.run_prompt(query, model=CHEAPEST_MODEL)
    # classification = re.sub(r'[^a-zA-Z0-9_]', '', raw_response)
    #
    # if raw_response in FORM_CLASSIFICATION:
    #     print(f"classified transcript as {classification}")
    #     return FormName.from_str(classification)
    #
    # default = None
    # print(
    #     f"WARNING: classified transcript unknown: {raw_response} -> {classification}; defaulting to {default}"
    # )
    # return default


def process_networking_transcript(
    gpt_client: OpenAiClient,
    data_entry: BaseDataEntry,
) -> List[PersonDataEntry]:
    # TODO: We should move task creation higher
    task = Task.create_task(
        workflow_name=FormName.CONTACTS.value, data_entry_id=data_entry.id
    )
    # TODO(P1, devx): With gpt-form-filler migration, we lost the task_id setting. Would be nice to have it back.
    # gpt_client.set_task_id(task_id=task.id)
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

    # TODO(P1, ux/reliability): Would be better to create / send emails as processed
    # instead of waiting to collect everything here.
    rest_of_the_crowd = []
    legit_results = []
    for i, person in enumerate(people_entries):
        if not person.should_show_full_contact_card():
            rest_of_the_crowd.append(person)
            continue

        person.form_data.set_field_value(
            # We use data_entry.created_at over .now(), cause created_at is best-effort when the recording happened.
            "recording_time",
            data_entry.created_at,
        )
        legit_results.append(person)

    # SAVE TO TASK
    for person in legit_results:
        task.add_generated_output(person.name, person.form_data)

    # UPDATE SPREADSHEET
    # TODO(P1, reliability): Once battle-tested, remove this
    try:
        sync_form_datas_to_gsheets(
            account_id=data_entry.account_id,
            form_datas=[person.form_data for person in legit_results],
        )
    except Exception as ex:
        print(f"ERROR: Cannot sync_people_to_gsheets cause {ex}")
        traceback.print_exc()

    # SEND EMAILS
    for person in legit_results:
        # if user.contact_method() == "email":
        send_networking_per_person_result(
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


def process_food_log_transcript(
    gpt_client: OpenAiClient,
    data_entry: BaseDataEntry,
) -> List[FormData]:
    print("process_food_log_transcript")

    task = Task.create_task(workflow_name="food_log", data_entry_id=data_entry.id)
    # TODO(P1, devx): With gpt-form-filler migration, we lost the task_id setting. Would be nice to have it back.
    # gpt_client.set_task_id(task.id)

    form_datas = run_food_ingredient_extraction(
        gpt_client=gpt_client,
        full_transcript=data_entry.output_transcript,
    )
    for i, form_data in enumerate(form_datas):
        # TODO(devx, P0): We need to generate an unique id for each row so we can better track it.
        task.add_generated_output(key=str(i), form_data=form_data)

    if not wait_for_email_updated_on_data_entry(data_entry.id, max_wait_seconds=3 * 60):
        print(
            f"WARNING: email missing for data_entry {data_entry.id} - cannot send results email"
        )

    sync_form_datas_to_gsheets(data_entry.account_id, form_datas=form_datas)

    return form_datas


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
    gpt_client = open_ai_client_with_db_cache()
    twilio_client = TwilioClient()

    # First Lambda
    if bucket == APP_UPLOADS_BUCKET:
        download_path = "/tmp/{}".format(os.path.basename(key))
        s3.download_file(bucket, key, download_path)
        # it can include folders, file extensions and such; ideally it should have metadata but unsure with presigned
        data_entry_id = parse_uuid_from_string(key)
        data_entry = process_app_upload(
            gpt_client=gpt_client,
            audio_or_video_filepath=download_path,
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


def process_generic_prompt(gpt_client, data_entry) -> str:
    print("process_generic_prompt for data_entry", data_entry.id)

    task = Task.create_task(workflow_name="generic_id", data_entry_id=data_entry.id)
    # TODO(P1, devx): With gpt-form-filler migration, we lost the task_id setting. Would be nice to have it back.
    # gpt_client.set_task_id(task.id)

    format_prompt = "Respond to this intake as a human executive assistant in a plaintext email: "
    result = gpt_client.run_prompt(format_prompt + data_entry.output_transcript, model=BEST_MODEL)

    transcript_prompt = """
        Just reformat this transcript, omit filler words, better sentence structure, keep the wording,
        add paragraphs if needed. Especially make sure you keep all mentioned facts and details.
    """
    # CHEAPEST_MODEL leads to overly short answers.
    transcription = gpt_client.run_prompt(transcript_prompt + data_entry.output_transcript, model=GPTo_MODEL)

    if not wait_for_email_updated_on_data_entry(data_entry.id, max_wait_seconds=3 * 60):
        print(
            f"WARNING: email missing for data_entry {data_entry.id} - cannot send results email"
        )

    # sync_form_datas_to_gsheets(data_entry.account_id, form_datas=form_datas)
    send_generic_result(
        account_id=data_entry.account_id,
        idempotency_id=data_entry.idempotency_id + "-generic-result",
        email_subject=f"Re: {data_entry.display_name}",
        email_body=result + "\n\n === Transcription === \n\n" + transcription,
    )

    return result


def second_lambda_handler_wrapper(data_entry: BaseDataEntry):
    if not wait_for_email_updated_on_data_entry(data_entry.id, max_wait_seconds=5 * 60):
        print(
            "WARNING: data entry has no associated email - we might be operating on an incomplete account"
        )
    gpt_client = open_ai_client_with_db_cache()
    acc: BaseAccount = BaseAccount.get_by_id(data_entry.account_id)
    print(f"gonna process transcript for account {acc.__dict__}")

    process_generic_prompt(gpt_client, data_entry)

    suggested_workflow_name = get_workflow_name(gpt_client, data_entry.output_transcript)
    if suggested_workflow_name == FormName.CONTACTS:
        process_networking_transcript(
            gpt_client=gpt_client,
            data_entry=data_entry,
        )
    if suggested_workflow_name == FormName.FOOD_LOG:
        process_food_log_transcript(
            gpt_client=gpt_client, data_entry=data_entry
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
            str(SKIP_PROCESSED_DATA_ENTRIES) == "1"
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
# TODO(P1, devx): Would be nice to get this working again, BUT my local supabase is somehow broken :(
# TODO(P2): Make this an automated-ish test
#  although would require further mocking of OpenAI calls from the test_.. stuff
if __name__ == "__main__":
    OUTPUT_BUCKET_NAME = None

    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        open_ai_client = open_ai_client_with_db_cache()
        # open_ai_client.run_prompt(f"test {time.time()}")

        test_case = "app"  # FOR EASY TEST CASE SWITCHING
        orig_data_entry = None
        if test_case == "app":
            app_account = Account.get_or_onboard_for_email(
                "test@dumpsheet.com", utm_source="test"
            )
            app_account.gsheet_id = "1CDW7dNs6CKkpyl7AEspAXinwp2NWYyQkyRTQtQwDynE"
            app_account.save()
            app_data_entry_id = BaseDataEntry.insert(
                account=app_account,
                display_name="test_display_name",
                idempotency_id=f"message-id-{time.time()}",
                input_type="app_upload",
            ).execute()
            test_parsing_too = parse_uuid_from_string(
                f"folder/{app_data_entry_id}.webm"
            )
            # TODO: remember what all this setup shabang does
            orig_data_entry = process_app_upload(
                gpt_client=open_ai_client,
                audio_or_video_filepath="testdata/brainfarting-boomergpt-mail.m4a",
                # audio_or_video_filepath="testdata/video-hvac-air-pump-cover.mp4",  # small video
                # audio_or_video_filepath="testdata/localonly/toastmasters-showcase-bricks.mp4",  # large video
                data_entry_id=test_parsing_too,
            )
        if test_case == "email":
            with open("testdata/boomergpt-mail-email", "rb") as handle:
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

        process_generic_prompt(
            gpt_client=open_ai_client,
            data_entry=orig_data_entry
        )

        workflow_name = get_workflow_name(
            open_ai_client, loaded_data_entry.output_transcript
        )
        if workflow_name == FormName.FOOD_LOG:
            process_food_log_transcript(
                gpt_client=open_ai_client, data_entry=loaded_data_entry
            )
        elif workflow_name == FormName.CONTACTS:
            # NOTE: We pass "orig_data_entry" here cause the loaded would include the results.
            process_networking_transcript(
                gpt_client=open_ai_client,
                data_entry=orig_data_entry,
            )

        EmailLog.save_last_email_log_to("result-app-app.html")
