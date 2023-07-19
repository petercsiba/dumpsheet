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
from db.email_log import EmailLog
from db.models import BaseDataEntry
from db.user import User
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

    attachment_file_paths = store_and_get_attachments_from_email(msg)

    user = User.get_or_create_using_rest(
        email=base_email_params.recipient,
        full_name=base_email_params.recipient_full_name,
    )

    inserted_id = (
        BaseDataEntry.insert(
            user_id=user.id,
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
                BaseDataEntry.user_id: None,
                BaseDataEntry.display_name: email_datetime.strftime("%B %d, %H:%M"),
                BaseDataEntry.created_at: email_datetime,
                BaseDataEntry.input_type: "email",
                BaseDataEntry.input_uri: bucket_url,
            },
        )
        .execute()
    )
    result = BaseDataEntry.get(BaseDataEntry.id == inserted_id)
    # TODO(P2, reliability): We should save the object *even earlier* in case of failures,
    #   but for now we have lambda retries so shrug.

    try:
        # TODO(peter): Verify if the swap base_email_params for get_email_reply_params_for_user works.
        confirmation_email_params = EmailLog.get_email_reply_params_for_user(
            user, base_email_params.subject, result.idempotency_id
        )
        # NOTE: We do NOT include the original attachments cause
        # botocore.exceptions.ClientError: An error occurred (InvalidParameterValue)
        # when calling the SendRawEmail operation: Message length is more than 10485760 bytes long: '24081986'.
        # confirmation_email_params.attachment_paths = attachment_file_paths
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
        audio_filepath = ffmpeg_convert_audio_to_mp4(attachment_file_path)
        if bool(audio_filepath):
            input_transcripts.append(
                gpt_client.transcribe_audio(audio_filepath=audio_filepath)
            )
    result.output_transcript = "\n\n".join(input_transcripts)

    return result
