import datetime
import traceback
from email import message_from_bytes
from email.utils import parsedate_to_datetime

from app.emails import (
    get_email_params_for_reply,
    send_confirmation,
    store_and_get_attachments_from_email,
)
from common.openai_client import OpenAiClient
from database.account import Account
from database.email_log import EmailLog
from database.models import BaseDataEntry
from input.common import ffmpeg_convert_audio_to_mp4


def process_email_input(
    gpt_client: OpenAiClient, raw_email, bucket_url=None
) -> BaseDataEntry:
    # TODO(P1, migration): Refactor the email processing to another function which returns some custom object maybe
    print(f"Read raw_email body with {len(raw_email)} bytes")

    # ======== Parse the email
    msg = message_from_bytes(raw_email)
    base_email_params = get_email_params_for_reply(msg)

    # Generate run-id as an idempotency key for re-runs
    if "Date" in msg:
        email_datetime = parsedate_to_datetime(msg["Date"])
    else:
        print(
            f"email msg does NOT have Date field, defaulting to now for email {base_email_params}"
        )
        email_datetime = datetime.datetime.now()

    attachment_file_paths = store_and_get_attachments_from_email(
        msg, file_name_prefix=str(email_datetime)
    )

    # To speak the truth, by sending an email they didn't yet signed up.
    # TODO(P0, ux): Test if this works after refactoring.
    account = Account.get_or_onboard_for_email(
        email=base_email_params.recipient,
        full_name=base_email_params.recipient_full_name,
    )

    inserted_id = (
        BaseDataEntry.insert(
            account=account,
            display_name=email_datetime.strftime("%B %d, %H:%M"),
            idempotency_id=msg["Message-ID"],
            created_at=email_datetime,
            input_type="email",
            input_uri=bucket_url,
        )
        .on_conflict(
            conflict_target=[BaseDataEntry.idempotency_id],
            # Postgres requires you to specify all fields to update explicitly.
            update={
                BaseDataEntry.account_id: account.id,
                BaseDataEntry.display_name: email_datetime.strftime("%B %d, %H:%M"),
                BaseDataEntry.created_at: email_datetime,
                BaseDataEntry.input_type: "email",
                BaseDataEntry.input_uri: bucket_url,
            },
        )
        .execute()
    )
    result: BaseDataEntry = BaseDataEntry.get(BaseDataEntry.id == inserted_id)

    try:
        confirmation_email_params = EmailLog.get_email_reply_params_for_account_id(
            account_id=account.id,
            idempotency_id=result.idempotency_id,
            subject=f"Re: {base_email_params.subject}",
            # NOTE: We do NOT include the original attachments cause in the reply
        )
        send_confirmation(
            params=confirmation_email_params, attachment_paths=attachment_file_paths
        )
    except Exception as err:
        print(
            f"ERROR: Could not send confirmation to {base_email_params.recipient} cause {err}"
        )
        traceback.print_exc()

    # For multiple attachments, we just merge them into one.
    input_transcripts = []
    for attachment_num, attachment_file_path in enumerate(attachment_file_paths):
        print(
            f"Processing attachment {attachment_num} out of {len(attachment_file_paths)}"
        )
        # TODO(ux, P1): Make sure the attachment_file_path is globally unique
        audio_filepath = ffmpeg_convert_audio_to_mp4(attachment_file_path)
        if bool(audio_filepath):
            input_transcripts.append(
                gpt_client.transcribe_audio(audio_filepath=audio_filepath)
            )
    result.output_transcript = "\n\n".join(input_transcripts)
    result.save()
    return result
