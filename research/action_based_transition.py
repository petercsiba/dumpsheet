import pandas as pd
import json
import os
import sys
from typing import Any, List
from json import JSONDecodeError

# For python research/action_based_transition.py
# TODO(P1, devx): make this work python -m research.action_based_transition
# When you run a Python file as a script, the directory containing that script is added to the Python path for that run.
# This means that Python can only import packages and modules
# that are in the same directory as the script or in a subdirectory of it.
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


from app.dynamodb import setup_dynamodb_local, teardown_dynamodb_local
from app.openai_client import OpenAiClient


def flatten_json(json_string: str) -> List:
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
            # Hack for output_people_entries dynamodb
            if "M" in entry:
                if "transcript" in entry["M"]:
                    person_transcript = entry["M"]["transcript"]
                    # print(f"{entry['M']['name']['S']}: {person_transcript}")
                    if "L" in person_transcript:
                        return entry['M']['name']['S'] + ": " + handle_entry(person_transcript["L"])
                    if "S" in person_transcript:
                        return entry['M']['name']['S'] + ": " + person_transcript["S"]
            return "\n".join(map(str, entry.values()))
        elif isinstance(entry, list):
            return "\n".join(map(handle_entry, entry))
        else:
            return str(entry)

    transformed = [handle_entry(entry) for entry in raw_data]
    # For input_transcripts
    # return "\n".join(transformed)
    return transformed


def draft_email(gpt_client: OpenAiClient, notes: str):
    queries = [
        """
As my executive assistant reading my notes do:
* write up to 3 shot bullet point summary of main facts, learnings
* suggest up to 3 google queries for me to look up further information on the person and their relevant companies
        """,
        """
Draft an actionable email as a response to the person based on my notes.
Make it 
* causal, 
* friendly, 
* using up same words, facts i used in the transcript to sound like me, 
while do NOT use
* jargon, 
* corp speak, 
* metaphors 
* nor too many superlatives.

The email based on my notes should be structured as following:

First part: 
Say Hi, 
Very brief and direct personalized summary of our last encounter, 
mention what I enjoyed OR appreciated in our conversation. 
Add a fact from my notes. Shortly explain why we should work on this together. 

Body part: 
For every actionable steps in the transcript write a matter-of-fact bullet point:
* 1st bullet: start with a bold point describing the action in several words
* 2nd bullet: proposed solution
* 3rd bullet add context, or example using words and facts from my notes

Closing part:
One personalized sentence to share my excitement, using the main topic and facts from my note..
        """
        # TODO(P1, quality): Consider making the style part as a follow-up query, we using the chat interface anyway.
    ]
    parts = []
    for query in queries:
        gpt_client.run_prompt(query + f"\n\nMy notes: {notes}")
    return "\n===============\n\n".join(parts)


process, local_dynamodb = setup_dynamodb_local()
# DynamoDB is used for caching between local test runs, spares both time and money!
open_ai_client = OpenAiClient(dynamodb=local_dynamodb)

# Load the csv
df = pd.read_csv('test/prod-dataentry-dump.csv')

# Raw inputs
# df['input_transcripts'] = df['input_transcripts'].apply(flatten_json)
#
# # print all values from 'input_transcripts' column
# for transcript in df['input_transcripts']:
#     if len(transcript) > 300:
#         print(transcript)
#         print("\n\n")

df['output_people_entries'] = df['output_people_entries'].apply(flatten_json)
i = 0
for transcripts in df['output_people_entries']:
    for transcript in transcripts:
        if len(transcript) <= 1000:
            continue
        i += 1
        if i > 10:
            print("done with ten transcripts")
            exit(0)

        # print(transcript)
        drafted_email = draft_email(open_ai_client, transcript)
        print(drafted_email)
        print("\n\n")


teardown_dynamodb_local(process)