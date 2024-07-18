import os
import random
import time

from app.app import process_networking_transcript
from common.openai_client import OpenAiClient
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from input.email import process_email_input


def process_file(gpt_client: OpenAiClient, file_contents):
    orig_data_entry = process_email_input(
        gpt_client=gpt_client,
        raw_email=file_contents,
    )

    people_entries = process_networking_transcript(
        gpt_client=gpt_client,
        data_entry=orig_data_entry,
    )

    print("====================================================")
    print(orig_data_entry.output_transcript)
    for person in people_entries:
        print(f"============  {person.name} ============ ")
        print(person.transcript)
        print("=== draft ===")
        print(person.next_draft)
        print("=== summary ===")
        summary_fields = person.form_data.to_display_tuples()
        print("\n * ".join([f"{key}: {value}" for key, value in summary_fields]))


dir_path = "testdata/katka-email-data-dump/"
# Use the os library to get a list of all files in that directory
file_list = os.listdir(dir_path)
# Get the current time
current_time = int(time.time())
print("===SEED: ", current_time)
random.seed(current_time)
random.shuffle(file_list)

with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
    open_ai_client = OpenAiClient(force_no_print_prompt=True)

    # Loop through each file
    for i, file in enumerate(file_list):
        if i > 3:
            print("reached transcript limit to prevent paying too much to OpenAI")
            break
        # Construct the full file path
        file_path = os.path.join(dir_path, file)

        # Only process if it is a file (not a sub-directory)
        if os.path.isfile(file_path):
            with open(file_path, "rb") as handle:
                process_file(open_ai_client, handle.read())
