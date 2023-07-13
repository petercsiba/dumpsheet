import pandas as pd
import json
from typing import Any
from json import JSONDecodeError


def flatten_json(json_string: str) -> str:
    """
    Flattens a JSON string by converting each entry in the deserialized Python object
    into a string and joining all strings with newline characters.

    Args:
        json_string: The JSON string to flatten.

    Returns:
        The flattened JSON string.
    """
    try:
        raw_data = json.loads(json_string)
    except JSONDecodeError:
        print(f"Couldn't decode the following JSON string:\n{json_string}")
        return ""

    def handle_entry(entry: Any) -> str:
        if isinstance(entry, dict):
            return "\n".join(map(str, entry.values()))
        elif isinstance(entry, list):
            return "\n".join(map(handle_entry, entry))
        else:
            return str(entry)

    flattened_data = "\n".join(handle_entry(entry) for entry in raw_data)
    return flattened_data


# Load the csv
df = pd.read_csv('test/prod-dataentry-dump.csv')

# Data Inspection
print(df.head())
print(df['input_transcripts'].head())

# Apply the function to the input_transcripts column
df['input_transcripts'] = df['input_transcripts'].apply(flatten_json)

# Save the updated DataFrame back to a CSV file
df.to_csv('test/prod-dataentry-dump_updated.csv', index=False)

# print all values from 'input_transcripts' column
for transcript in df['input_transcripts']:
    print(transcript)
    print("\n\n")