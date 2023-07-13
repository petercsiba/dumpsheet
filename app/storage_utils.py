import os
from typing import Tuple, Optional

from aws_utils import is_running_in_aws, get_boto_s3_client

s3 = get_boto_s3_client()


def pretty_filesize_int(file_size: int) -> str:
    return f"{file_size / (1024 * 1024):.2f}MB"


def pretty_filesize_path(file_path: str) -> str:
    return pretty_filesize_int(os.path.getsize(file_path))


def get_fileinfo(file_handle):
    return f"File {file_handle.name} is {pretty_filesize_path(file_handle.name)}"


def mkdir_safe(directory_name):
    path = os.path.join(os.getcwd(), directory_name)
    if os.path.exists(directory_name):
        print(f"direction already exists {path}")
        return
    print(f"creating directory {path}")
    try:
        os.mkdir(path)
        print(f"Directory {directory_name} created successfully!")
    except FileExistsError:
        print(f"Directory {directory_name} already exists.")
    except Exception as e:
        print(f"An error occurred while creating directory {directory_name}: {e}")


def write_output_to_local_and_bucket(
        data,
        suffix: str,
        local_output_prefix: str,
        content_type: str,
        bucket_name: Optional[str],
        bucket_object_prefix: Optional[str],
) -> Tuple[str, str]:
    local_filepath = f"{local_output_prefix}{suffix}"
    print(f"Gonna write some data to {local_filepath}")
    with open(local_filepath, "w") as file_handle:
        file_handle.write(data)
    print(f"Written {pretty_filesize_path(local_filepath)} to {local_filepath}")

    bucket_key = None
    if is_running_in_aws():
        bucket_key = f"{bucket_object_prefix}{suffix}"
        print(f"Uploading that data to S3://{bucket_name}/{bucket_key}")
        s3.upload_file(
            local_filepath,
            bucket_name,
            bucket_key,
            ExtraArgs={'ContentType': content_type},
        )

    return local_filepath, bucket_key
