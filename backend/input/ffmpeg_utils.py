import os
import subprocess
import time
import traceback
from typing import List

from pydub import AudioSegment


WHISPER_API_MAX_FILE_SIZE = 25 * 1024 * 1024
WHISPER_API_CHUNK_TARGET_FILE_SIZE = 20 * 1024 * 1024
WHISPER_API_OVERLAP_MS = 3000
WHISPER_API_MIN_LAST_CHUNK_MS = 15000


# Here object_prefix is used for both local, response attachments and buckets.
# BEWARE: This requires the heavy ffmpeg to be installed on the machine (which is a quite large dependency).
def deal_with_potentially_large_audio_file(
        audio_file_path,
        target_file_size:int = WHISPER_API_CHUNK_TARGET_FILE_SIZE,
        overlap_ms: int = 3000
) -> List[str]:
    # https://platform.openai.com/docs/guides/speech-to-text/longer-inputs
    audio_file_size = os.path.getsize(audio_file_path)
    audio_file_size_mb = round(audio_file_size / 1024 / 1024, 2)
    if audio_file_size <= WHISPER_API_MAX_FILE_SIZE:
        return [audio_file_path]

    audio_format = os.path.splitext(audio_file_path)[-1][1:].lower()
    print(f"Audio file is too large for Whisper API: {audio_file_size_mb} MB for {audio_format} "
          f"-> Splitting it into smaller parts about {WHISPER_API_CHUNK_TARGET_FILE_SIZE / 1024 / 1024} MB each.")
    audio = AudioSegment.from_file(audio_file_path, format=audio_format)

    # Calculate the duration per MB to determine the length of each chunk
    duration_ms = len(audio)  # Get the duration of the entire audio in milliseconds
    size_per_ms = audio_file_size / duration_ms  # B per millisecond of audio
    chunk_size_ms = target_file_size / size_per_ms  # Target chunk size 20MB in milliseconds

    start_time = time.time()
    chunks = []
    total_file_size = 0
    for i, chunk_start in enumerate(range(0, duration_ms, int(chunk_size_ms))):
        chunk_end = min(chunk_start + int(chunk_size_ms) + overlap_ms, duration_ms)
        # Ensure the last chunk is at least 15 seconds long
        should_early_exit = False
        if duration_ms != chunk_end and duration_ms - chunk_end < WHISPER_API_MIN_LAST_CHUNK_MS:
            print("Last-ish chunk is too short, extending it to 15 seconds")
            chunk_end = duration_ms  # Merge the remaining audio into the current chunk
            should_early_exit = True

        chunk = audio[chunk_start:chunk_end]
        chunk_filepath = f"{audio_file_path}_part_{i+1}.{audio_format}"

        export_format_map = {
            "m4a": "ipod",
            "mp3": "mp3",
            "webm": "webm",
            "wav": "wav"
        }
        export_format = export_format_map.get(audio_format, audio_format)
        chunk.export(chunk_filepath, format=export_format)

        chunk_filesize = os.path.getsize(chunk_filepath)
        total_file_size += chunk_filesize
        chunk_duration_sec = round((chunk_end - chunk_start) / 1000, 2)
        print(f"Chunk {i+1}: duration {chunk_duration_sec} seconds {round(chunk_filesize / 1024 / 1024, 2)} MB saved as {chunk_filepath}")

        if chunk_filesize > WHISPER_API_MAX_FILE_SIZE:
            print(f"ERROR: Chunk {i+1} is still too large, lower WHISPER_API_CHUNK_TARGET_FILE_SIZE")
            # Recurse trying smaller target chunks, without overlap just to be safe.
            chunks.extend(deal_with_potentially_large_audio_file(chunk_filepath, target_file_size=target_file_size // 2, overlap_ms=0))
        else:
            chunks.append(chunk_filepath)

        if should_early_exit:
            print("should_early_exit chunk loop true, breaking loop")
            break

    duration_in_seconds = time.time() - start_time
    mbs_processed_per_second = round(audio_file_size / 1024 / 1024 / duration_in_seconds, 2)
    print(
        f"Split up {round(duration_in_seconds, 2)} seconds at speed of {mbs_processed_per_second} MB/seconds into {len(chunks)} chunks."
    )
    print(f"Input size: {audio_file_size_mb} MB, Output size: {round(total_file_size / 1024 / 1024, 2)} MB.")

    return chunks


def ffmpeg_convert_to_whisper_supported_audio(input_file_path: str) -> List[str]:
    # I did a super-quick test on this (and I should have done way before), but it seems that m4a works best.
    # OR just keeping the original format, but that's not always possible.
    # https://chatgpt.com/share/66e34f17-6bb8-8005-8d3f-44764e481761
    primary_target_format = "m4a"  # when changing this, also change the -acodec below
    # We omit formats mp4 and mpeg, as those can be videos too.
    supported_formats = ["m4a", "mp3", "webm", "wav"]
    if any(input_file_path.endswith(supported_format) for supported_format in supported_formats):
        print(f"File is already in a supported format, skipping ffmpeg conversion for: {input_file_path}")
        return deal_with_potentially_large_audio_file(input_file_path)

    output_file_path = input_file_path + f".{primary_target_format}"
    print(f"Running ffmpeg on {input_file_path} outputting to {output_file_path}")
    input_file_size = os.path.getsize(input_file_path) / 1024 / 1024  # in MB
    print(f".. Expected ffmpeg runtime is {2 * input_file_size} seconds (about 1 second per 0.5MB of input file size).")

    # TODO(P1, cost): Consider deploying Whisper by ourselves, BUT that can be quite expensive anyway.
    # TODO(P2, ux): Consider optimizing for file-size for faster uploads. For example:
    # ffmpeg -i audio.mp3 -vn -map_metadata -1 -ac 1 -c:a libopus -b:a 12k -application voip audio.ogg
    # Opus is one of the highest quality audio encoders at low bitrates, and is supported by Whisper in ogg container.
    # https://community.openai.com/t/whisper-api-increase-file-limit-25-mb/566754
    # Or this guy MP3 Bit Rate: 16 kbps Sample Rate: 12 kHz Channels: mono
    # https://dev.to/mxro/optimise-openai-whisper-api-audio-format-sampling-rate-and-quality-29fj

    try:
        start_time = time.time()
        # -y to force overwrite,
        #      "-acodec", "aac",  # Use AAC codec (default for M4A)
        # For higher quality larger file outputs (increases file size by 80%):
        #      "-b:a", "320k",  # Set audio bitrate to 320kbps for best quality (can be adjusted)
        #      "-ar", "44100",  # Set sample rate (standard is 44100 Hz)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "warning", "-i", input_file_path,
             "-vn",  # Disable the video stream (audio-only)
             output_file_path],
            check=True,
        )
        duration_in_seconds = time.time() - start_time
        mbs_processed = os.path.getsize(output_file_path) / 1024 / 1024  # in MB
        mbs_processed_per_second = round(mbs_processed / duration_in_seconds, 2)
        print(f"Converted in {round(duration_in_seconds, 2)} seconds at speed of {mbs_processed_per_second} MB/second saved as: {output_file_path}")
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg error occurred: {e}")
        traceback.print_exc()
        return []

    return deal_with_potentially_large_audio_file(output_file_path)


if __name__ == "__main__":
    print(deal_with_potentially_large_audio_file("testdata/localonly/toastmasters-showcase-bricks.mp4.m4a"))
