import uuid

from app.emails import (
    send_app_upload_confirmation,
    wait_for_email_updated_on_data_entry,
)
from gpt_form_filler.openai_client import OpenAiClient

from common.aws_utils import is_running_in_aws
from common.gpt_utils import transcribe_audio_chunk_filepaths
from database.account import Account
from database.data_entry import STATE_UPLOAD_DONE
from database.email_log import EmailLog
from database.models import BaseDataEntry
from input.ffmpeg_utils import ffmpeg_convert_to_whisper_supported_audio


# App uploads are in webm format - which should work with Whisper (but then they claimed the same for .wav).
def process_app_upload(
    gpt_client: OpenAiClient, audio_or_video_filepath: str, data_entry_id: uuid.UUID
) -> BaseDataEntry:
    print(f"process_app_upload for data_entry_id {data_entry_id}")

    # We only send confirmation emails if the email already exists, i.e. we do not wait much.
    maybe_send_app_upload_confirmation_email(data_entry_id)

    # First check if everything is fine
    data_entry: BaseDataEntry = BaseDataEntry.get_by_id(data_entry_id)

    # Browser standards now suggest .webm format, but with so many client versions you cannot guarantee that.
    converted_audio_filepath_chunks = ffmpeg_convert_to_whisper_supported_audio(audio_or_video_filepath)
    output_transcript = transcribe_audio_chunk_filepaths(gpt_client, converted_audio_filepath_chunks)

    data_entry.output_transcript = output_transcript
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
    acc: Account = Account.get_by_id(data_entry.account_id)
    first_time_use = acc.gsheet_id is None

    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=data_entry.account_id,
        idempotency_id=data_entry.idempotency_id,
        subject=None,
    )
    try:
        send_app_upload_confirmation(params=email_params, first_time_use=first_time_use)
    except Exception as err:
        print(
            f"ERROR: Could not send app upload confirmation to {email_params.recipient} cause {err}"
        )
