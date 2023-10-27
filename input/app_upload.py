import uuid

from app.emails import (
    send_app_upload_confirmation,
    wait_for_email_updated_on_data_entry,
)
from common.openai_client import OpenAiClient
from database.account import Account
from database.data_entry import STATE_UPLOAD_DONE
from database.email_log import EmailLog
from database.models import BaseDataEntry
from input.common import ffmpeg_convert_audio_to_mp4


# App uploads are in webm format - which should work with Whisper (but then they claimed the same for .wav).
def process_app_upload(
    gpt_client: OpenAiClient, audio_filepath: str, data_entry_id: uuid.UUID
) -> BaseDataEntry:
    print(f"process_app_upload for data_entry_id {data_entry_id}")

    # We only send confirmation emails if the email already exists, i.e. we do not wait much.
    maybe_send_app_upload_confirmation_email(data_entry_id)

    # First check if everything is fine
    data_entry: BaseDataEntry = BaseDataEntry.get_by_id(data_entry_id)

    # Even though browsers upload webm files, and my works (on the desktop), clearly it isn't standardized.
    converted_audio_filepath = ffmpeg_convert_audio_to_mp4(audio_filepath)

    data_entry.output_transcript = gpt_client.transcribe_audio(
        audio_filepath=converted_audio_filepath
    )
    data_entry.state = STATE_UPLOAD_DONE
    data_entry.save()

    # We try to send confirmation emails again if the email already exists, i.e. we do not wait much.
    maybe_send_app_upload_confirmation_email(data_entry_id)

    return data_entry


def maybe_send_app_upload_confirmation_email(data_entry_id: uuid.UUID):
    if not wait_for_email_updated_on_data_entry(
        data_entry_id, max_wait_seconds=20, wait_cycle_seconds=5
    ):
        print("skip maybe_send_app_upload_confirmation_email cause no email yet")
        return

    data_entry: BaseDataEntry = BaseDataEntry.get_by_id(data_entry_id)
    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=data_entry.account_id,
        idempotency_id=data_entry.idempotency_id,
        # We used to include the timestamp, but gets harder with timezones. We would need to geo-locate it and stuff.
        subject="Confirmation - I have received your voice recording upload",
    )
    acc: Account = Account.get_by_id(data_entry.account_id)
    heads_up_spreadsheet_email = acc.gsheet_id is None
    try:
        send_app_upload_confirmation(
            params=email_params, heads_up_spreadsheet_email=heads_up_spreadsheet_email
        )
    except Exception as err:
        print(
            f"ERROR: Could not send app upload confirmation to {email_params.recipient} cause {err}"
        )
