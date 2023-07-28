import datetime
import uuid

from common.openai_client import OpenAiClient
from database.models import BaseDataEntry
from input.common import ffmpeg_convert_audio_to_mp4


# App uploads are in webm format - which should work with Whisper (but then they claimed the same for .wav).
def process_app_upload(
    gpt_client: OpenAiClient, audio_filepath: str, data_entry_id: uuid.UUID
) -> BaseDataEntry:
    print(f"process_app_upload for {data_entry_id}")
    # First check if everything is fine
    data_entry: BaseDataEntry = BaseDataEntry.get_by_id(data_entry_id)

    # Even though browsers upload webm files, and my works (on the desktop), clearly it isn't standardized.
    converted_audio_filepath = ffmpeg_convert_audio_to_mp4(audio_filepath)

    data_entry.output_transcript = gpt_client.transcribe_audio(
        audio_filepath=converted_audio_filepath
    )
    data_entry.processed_at = datetime.datetime.now()
    data_entry.save()
    return data_entry
