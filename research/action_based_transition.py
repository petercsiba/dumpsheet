import json
from json import JSONDecodeError
from typing import Any, List

import pandas as pd

from app.dynamodb import setup_dynamodb_local, teardown_dynamodb_local
from app.networking_dump import summarize_transcripts_to_person_data_entries
from common.openai_client import OpenAiClient


def get_query_for_actionable_email(actions: List) -> str:
    return (
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
For every of these actions:
 """
        + "\n* ".join(actions)
        + """
 write a matter-of-fact bullet point:
* 1st bullet: start with a bold point describing the action in several words
* 2nd bullet: proposed solution
* 3rd bullet add context, or example using words and facts from my notes

Closing part:
One personalized sentence to share my excitement, using the main topic and facts from my note.
    """
    )


def get_query_for_nice_to_meet_you(follow_up: str) -> str:
    return """From the notes on the following person
please generate a short outreach message written in style of
a "smooth casual friendly yet professional person",
ideally adjusted to the talking style from the note,
to say that "{}"  (use up to 250 characters)
Please make sure that:
* to mention what I enjoyed OR appreciated in the conversation
* include a fact / a hobby / an interest from our conversation
* omit any sensitive information, especially money
Only output the resulting message - do not use double quotes at all.
""".format(
        follow_up
    )


def extract_transcript(json_string: str) -> str:
    """
    Flattens a JSON string by converting each entry in the deserialized Python object
    into a string and joining all strings with newline characters.

    Args:
        json_string: The JSON string to flatten.

    Returns:
        The flattened JSON string.
    """
    try:
        if isinstance(json_string, str):
            raw_data = json.loads(json_string)
        else:
            raw_data = json_string
    except JSONDecodeError:
        print(f"Couldn't decode the following JSON string:\n{json_string}")
        return ""
    # print(f"extract_transcript: {raw_data}")

    def handle_entry(entry: Any) -> str:
        if isinstance(entry, dict):
            # Hack for output_people_entries dynamodb
            if "M" in entry:
                if "transcript" in entry["M"]:
                    person_transcript = entry["M"]["transcript"]
                    # print(f"{entry['M']['name']['S']}: {person_transcript}")
                    if "L" in person_transcript:
                        return (
                            entry["M"]["name"]["S"]
                            + ": "
                            + handle_entry(person_transcript["L"])
                        )
                    if "S" in person_transcript:
                        return entry["M"]["name"]["S"] + ": " + person_transcript["S"]
            return "\n".join(map(str, entry.values()))
        elif isinstance(entry, list):
            return "\n".join(map(handle_entry, entry))
        else:
            return str(entry)

    transformed = [handle_entry(entry) for entry in raw_data]
    # For input_transcripts
    return "\n".join(transformed)


def draft_email(gpt_client: OpenAiClient, notes: str, follow_ups: List):
    summary_query = """
As my executive assistant reading my notes do:
* write up to 3 shot bullet point summary of main facts, learnings
* suggest up to 3 google queries for me to look up further information on the person and their relevant companies
        """
    # TODO(P1, quality): Consider making the style part as a follow-up query, we using the chat interface anyway.
    if len(follow_ups) == 1:
        follow_up_query = get_query_for_nice_to_meet_you(follow_ups[0])
    else:
        follow_up_query = get_query_for_actionable_email(follow_ups)

    queries = [follow_up_query, summary_query]
    parts = []
    for query in queries:
        parts.append(
            gpt_client.run_prompt(query + f"\n\nMy notes: {notes}", print_prompt=True)
        )
    return "\n===============\n\n".join(parts)


process, local_dynamodb = setup_dynamodb_local()
# DynamoDB is used for caching between local test runs, spares both time and money!
open_ai_client = OpenAiClient(dynamodb=local_dynamodb)

# Load the csv
df = pd.read_csv("test/prod-dataentry-dump.csv")

# Raw inputs
df["input_transcripts"] = df["input_transcripts"].apply(extract_transcript)

# # print all values from 'input_transcripts' column
i = 0
for transcript in df["input_transcripts"]:
    if len(transcript) <= 1000:
        continue
    i += 1
    if i > 10:
        print("done with ten transcripts")
        exit(0)

    # TODO(P1, reliability/quality): Try to simplify this with some Entity extraction process.
    pde = summarize_transcripts_to_person_data_entries(
        open_ai_client, person_to_transcript={"": transcript}
    )[0]
    # ["Great to meet you, let me know if I can ever do anything for you!"]
    # print(transcript)
    drafted_email = draft_email(open_ai_client, transcript, pde.follow_ups)
    print(drafted_email)
    print("\n\n")


teardown_dynamodb_local(process)
