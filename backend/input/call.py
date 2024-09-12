import datetime
import os
import re
from typing import Optional

from common.aws_utils import is_running_in_aws
from common.config import SUPPORT_EMAIL
from gpt_form_filler.openai_client import OpenAiClient
from common.twillio_client import TwilioClient
from database.account import Account
from database.data_entry import STATE_UPLOAD_DONE
from database.models import BaseDataEntry
from input.ffmpeg_utils import ffmpeg_convert_to_whisper_supported_audio


def strip_empty_tokens(text):
    empty_tokens = ["none", "undefined", "null"]
    # Create a regex pattern that matches the empty tokens, case insensitive
    pattern = re.compile(
        "|".join("\\b{}\\b".format(token) for token in empty_tokens), re.IGNORECASE
    )
    # Substitute all matches with an empty string
    stripped_text = pattern.sub("", text)
    return stripped_text.strip()  # Remove leading/trailing white space


def process_voice_recording_input(
    gpt_client: OpenAiClient,
    twilio_client: Optional[TwilioClient],
    bucket_url: Optional[str],  # for tracking purposes
    event_timestamp: datetime.datetime,
    call_sid: str,
    voice_file_data: bytes,
    phone_number: str,
    full_name: str,
    phone_carrier_info: Optional[str] = None,
) -> BaseDataEntry:
    full_name = strip_empty_tokens(
        full_name
    )  # Sometimes getting "Undefined Peter Csiba"
    account = Account.get_or_onboard_for_phone(
        phone=phone_number,
        full_name=full_name,
        onboarding_kwargs={"phone_carrier_info": phone_carrier_info},
    )

    if account.get_email() is None:
        msg = (
            # (size {pretty_filesize_int(len(voice_file_data))})
            f"Hi boss, Voxana here. I have received your voicemail.\n"
            "To get your results into your inbox, please reply with a sms containing your email address.\n"
            f"In case of troubles, you can always reach my supervisors at {SUPPORT_EMAIL}.\n"
            "Bye!"
            # "To opt-out , please respond with 'NO'. Thank you!"
        )
        if bool(twilio_client):
            twilio_client.send_sms(
                phone_number,
                body=msg,
            )
        else:
            print(f"SKIPPING send_sms cause no twilio_client would have sent {msg}")

    # TODO: We probably need to support their timezone :/ (or drop this identifier).
    nice_ts = event_timestamp.strftime("%B %d, %H:%M")
    inserted_id = (
        BaseDataEntry.insert(
            created_at=event_timestamp,
            display_name=f"Voicemail from {nice_ts}",
            idempotency_id=call_sid,
            input_type="voicemail",
            input_uri=bucket_url,
            account_id=account.id,
            state=STATE_UPLOAD_DONE,
        )
        .on_conflict(
            conflict_target=[BaseDataEntry.idempotency_id],
            # Postgres requires you to specify all fields to update explicitly on conflict :/
            update={
                BaseDataEntry.created_at: event_timestamp,
                BaseDataEntry.display_name: f"Voicemail from {nice_ts}",
                BaseDataEntry.input_type: "voicemail",
                BaseDataEntry.input_uri: bucket_url,
                BaseDataEntry.account_id: None,
            },
        )
        .execute()
    )
    res = BaseDataEntry.get(BaseDataEntry.id == inserted_id)

    # TODO(P3, cleanup): Would be nice to move the filesystem off this file.
    file_path = os.path.join("/tmp/", call_sid)
    with open(file_path, "wb") as f:
        f.write(voice_file_data)
    audio_filepath = ffmpeg_convert_to_whisper_supported_audio(file_path)
    if bool(audio_filepath):
        res.output_transcript = gpt_client.transcribe_audio(
            audio_filepath=audio_filepath,
            prompt_hint="phone call to my assistant",
            use_cache_hit=not is_running_in_aws(),
        )

    res.save()
    return res
