from typing import List

from gpt_form_filler.openai_client import OpenAiClient

from common.aws_utils import is_running_in_aws


def transcribe_audio_chunk_filepaths(gpt_client: OpenAiClient, audio_filepaths: List[str]) -> str:
    if len(audio_filepaths) == 0:
        print("WARNING: NO AUDIO PROVIDED in process_audio_chunk_filepaths")
        return "NO AUDIO PROVIDED"
    if len(audio_filepaths) > 1:
        # TODO(P2, ux/devx): We can parallelize this, but it's not a priority (15min lambda limit though)
        print(f"Provided {len(audio_filepaths)} audio files, will process them one-by-one in sequence.")

    transcribed_chunks = [
        gpt_client.transcribe_audio(
            audio_filepath=filepath,
            prompt_hint="voice memo",
            use_cache_hit=not is_running_in_aws()
        ) for filepath in audio_filepaths
    ]
    return " ".join(transcribed_chunks)
