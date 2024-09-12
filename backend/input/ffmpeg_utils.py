import subprocess
import traceback
from typing import Optional


# Here object_prefix is used for both local, response attachments and buckets.
# BEWARE: This requires the heavy ffmpeg to be installed on the machine (which is a quite large dependency).
def ffmpeg_convert_to_whisper_supported_audio(file_path: str) -> Optional[str]:
    # I did a super-quick test on this (and I should have done way before), but it seems that m4a works best.
    # (or keeping the original format, but that's not always possible)
    # https://chatgpt.com/share/66e34f17-6bb8-8005-8d3f-44764e481761
    primary_target_format = "m4a"  # when changing this, also change the -acodec below
    # We omit formats mp4 and mpeg, as those can be videos too.
    supported_formats = ["m4a", "mp3", "webm", "wav"]
    if any(file_path.endswith(supported_format) for supported_format in supported_formats):
        print(f"File is already in a supported format, skipping ffmpeg conversion for: {file_path}")
        return file_path

    audio_file_path = file_path + f".{primary_target_format}"
    print(f"Running ffmpeg on {file_path} outputting to {audio_file_path}")

    # TODO(P1, cost): Consider deploying Whisper by ourselves, BUT that can be quite expensive anyway.
    # TODO(P2, ux): Consider optimizing for file-size for faster uploads. For example:
    # ffmpeg -i audio.mp3 -vn -map_metadata -1 -ac 1 -c:a libopus -b:a 12k -application voip audio.ogg
    # Opus is one of the highest quality audio encoders at low bitrates, and is supported by Whisper in ogg container.
    # https://community.openai.com/t/whisper-api-increase-file-limit-25-mb/566754
    # Or this guy MP3 Bit Rate: 16 kbps Sample Rate: 12 kHz Channels: mono
    # https://dev.to/mxro/optimise-openai-whisper-api-audio-format-sampling-rate-and-quality-29fj

    try:
        # -y to force overwrite,
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "warning", "-i", file_path,
             "-vn",  # Disable the video stream (audio-only)
             "-acodec", "aac",  # Use AAC codec (default for M4A)
             "-b:a", "320k",  # Set audio bitrate to 320kbps for best quality (can be adjusted)
             "-ar", "44100",  # Set sample rate (standard is 44100 Hz)
             audio_file_path],
            check=True,
        )
        print(f"Converted file saved as: {audio_file_path}")
        # TODO(P0, devx): Make sure the output files is below 25MB OR do this in gpt-form-filler:
        #   https://platform.openai.com/docs/guides/speech-to-text/longer-inputs
        #   NOTE that `pydub` requires `ffmpeg` to be installed on the machine - so we should do it here.
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg error occurred: {e}")
        traceback.print_exc()
        return None

    return audio_file_path
