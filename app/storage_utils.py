import csv
import os


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
    fieldnames = data[0].keys()
    print(f"write_to_csv {len(data)} rows with fieldnames {fieldnames}")

    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        # ValueError: dict contains fields not in fieldnames: 'Characteristics and personality in up to 200 words', ...
        writer.writerows(data)