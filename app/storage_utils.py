import csv
import os


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
