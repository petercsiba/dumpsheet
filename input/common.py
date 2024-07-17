import subprocess
import traceback


# Here object_prefix is used for both local, response attachments and buckets.
# NOTE: This requires the heavy ffmpeg to be installed on the machine.
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
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg error occurred: {e}")
        traceback.print_exc()
        return None
    return audio_file
