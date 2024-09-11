import subprocess
import traceback


# Here object_prefix is used for both local, response attachments and buckets.
# NOTE: This requires the heavy ffmpeg to be installed on the machine.
# TODO(P0, ux): Support also video formats, unsure why I have picked mp4.
def ffmpeg_convert_audio_to_mp4(file_path):
    audio_file = file_path + ".mp4"
    print(f"Running ffmpeg on {file_path} outputting to {audio_file}")
    try:
        # -y to force overwrite in case the file already exists
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", file_path, audio_file],
            check=True,
        )
        print(f"Converted file saved as: {audio_file}")
        # TODO(P0, devx): Make sure the output files is below 25MB OR do this in gpt-form-filler:
        #   https://platform.openai.com/docs/guides/speech-to-text/longer-inputs
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg error occurred: {e}")
        traceback.print_exc()
        return None
    return audio_file
