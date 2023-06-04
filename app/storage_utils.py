import boto3
import csv
import os

from aws_utils import is_running_in_aws

s3 = boto3.client('s3')


def pretty_filesize(file_path):
    return f"{os.path.getsize(file_path) / (1024 * 1024):.2f}MB"


def get_fileinfo(file_handle):
    return f"File {file_handle.name} is {pretty_filesize(file_handle.name)}"


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


def write_to_csv(data, output_file):
    # In first row we trust
    fieldnames = data[0].keys()
    print(f"write_to_csv {len(data)} rows with fieldnames {fieldnames}")

    # All this mambo-jambo just to fix
    # ValueError: dict contains fields not in fieldnames: 'todo_full_name', 'todo_profile_url'
    safe_data = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            print(f"write_to_csv skipping row {i} as not a dict! {row}")
            continue
        missing_keys = set(fieldnames) - set(row.keys())
        safe_row = dict(row)
        if len(missing_keys) > 0:
            print(f"write_to_csv row {i} has missing keys filling in nones for {missing_keys}")
            for key in missing_keys:
                safe_row[key] = None
        safe_data.append(safe_row)

    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(safe_data)
    print(f"write_to_csv written {len(safe_data)} rows with {len(fieldnames)} columns")


def write_output_to_local_and_bucket(
        data,
        suffix: str,
        local_output_prefix: str,
        content_type: str,
        bucket_name: str,
        bucket_object_prefix: str,
):
    local_filepath = f"{local_output_prefix}{suffix}"
    print(f"Gonna write some data to {local_filepath}")
    # This is kinda hack
    if suffix.endswith(".csv"):
        write_to_csv(data, local_filepath)
    else:
        with open(local_filepath, "w") as file_handle:
            file_handle.write(data)
    print(f"Written {pretty_filesize(local_filepath)} to {local_filepath}")

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
