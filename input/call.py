import datetime
import os
from typing import Optional

from app.datashare import User
from app.dynamodb import DynamoDBManager
from common.openai_client import OpenAiClient
from common.storage_utils import pretty_filesize_int
from common.twillio_client import TwilioClient
from db.models import BaseDataEntry
from input.common import ffmpeg_convert_audio_to_mp4


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
) -> [User, BaseDataEntry]:
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

    user = dynamodb.get_or_create_user(
        email_address=None, phone_number=phone_number, full_name=full_name
    )
    nice_ts = event_timestamp.strftime("%B %d, %H:%M")
    inserted_id = (
        BaseDataEntry.insert(
            created_at=event_timestamp,
            display_name=f"Call from {nice_ts}",
            idempotency_id=call_sid,
            input_type="call",
            input_uri=bucket_url,
            # TODO(P0): Set it once it is uuid
            user_id=None,
            # user_id=user.user_id,
        )
        .on_conflict(
            conflict_target=[BaseDataEntry.idempotency_id],
            # Postgres requires you to specify all fields to update explicitly.
            update={
                BaseDataEntry.created_at: event_timestamp,
                BaseDataEntry.display_name: f"Call from {nice_ts}",
                BaseDataEntry.input_type: "call",
                BaseDataEntry.input_uri: bucket_url,
                BaseDataEntry.user_id: None,
            },
        )
        .execute()
    )
    result = BaseDataEntry.get(BaseDataEntry.id == inserted_id)

    # TODO(P3, cleanup): Would be nice to move the filesystem off this file.
    file_path = os.path.join("/tmp/", call_sid)
    with open(file_path, "wb") as f:
        f.write(voice_file_data)
    audio_filepath = ffmpeg_convert_audio_to_mp4(file_path)
    if bool(audio_filepath):
        result.output_transcript = gpt_client.transcribe_audio(
            audio_filepath=audio_filepath
        )

    result.save()
    return user, result
