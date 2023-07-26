import json
from dataclasses import asdict
from typing import Dict, List, Optional

from app.datashare import PersonDataEntry
from common.openai_client import (
    DEFAULT_MODEL,
    OpenAiClient,
    gpt_response_to_json,
    gpt_response_to_json_list,
    num_tokens_from_string,
)

MIN_TRANSCRIPT_LENGTH = 80  # characters, can prevent some "hallucinations"
# TODO(P1, features): Go bi-model with Claude which can handle 100k tokens for longer dumps
#  https://www.anthropic.com/index/claude-2
MAX_TRANSCRIPT_TOKEN_COUNT = 2500  # words


# TODO(P0, ux): We should extract the full named entity graph here (node, person/company/...), (edge, "relationship")
#   here extraction might be simple, but to actually make it valuable might be harder.
# TODO(P1, devx): Historically, this query give me most of the headaches.
#   * GPT-4 suggests using Named Entity Recognition (NER)
#   * If it remains a problem - maybe just do it one-by-one, screw token cost.
def named_entity_recognition(gpt_client: OpenAiClient, full_transcript: str) -> List:
    # NOTE: We shorten the string by words cause easier, but we better estimate the token count by OpenAI counter.
    token_count = num_tokens_from_string(full_transcript)
    print(f"Transcript has {token_count} words")

    # Make sure to include the whole string without gaps.
    # TODO(P1, quality): Eventually we would need to implement processing a larger input.
    if token_count > MAX_TRANSCRIPT_TOKEN_COUNT:
        print(
            f"ERROR: raw_transcript too long ({token_count}), truncating to {MAX_TRANSCRIPT_TOKEN_COUNT}"
        )
        transcript_words = full_transcript.split()
        full_transcript = " ".join(transcript_words[:MAX_TRANSCRIPT_TOKEN_COUNT])

    # TODO(P1, research): Understand if GPT function calling can help us. From first read it seems that the use case
    #   is for GPT to call other APIs. But they mention `extract_people_data` from a Wikipedia article
    # https://openai.com/blog/function-calling-and-other-api-updates
    query_people = """
    Find all the people mentioned in my note, be careful that I might be referring to the same person
     differently usually in the order of full name, first name and he/she.
    For all those people, please output a valid json list of strings
    where each element contains a name or a short unique descriptive identifier of that person".
    My note: {}
        """.format(
        full_transcript
    )
    raw_response = gpt_client.run_prompt(query_people)
    if raw_response is None:
        print("WARNING: Likely no people found in the input transcript")
        return []
    people = gpt_response_to_json_list(raw_response)
    print(f"People: {json.dumps(people)}")
    return people


# Return a dict(name -> context)
# My mistake was that I tried to optimize token count, returning only indexes, which made the code very complicated.
def extract_context_per_person(
    gpt_client: OpenAiClient, full_transcript: str, people: List
) -> Dict:
    if people is None or len(people) == 0:
        return {}

    result = {}
    size = 10 if DEFAULT_MODEL.startswith("gpt-4") else 5
    # I generated this with chat-gpt, so feel free to use it to explain it.
    sub_lists_of_people = [people[i : i + size] for i in range(0, len(people), size)]
    for sublist in sub_lists_of_people:
        query_mentions = """
For each of the following people, extract all substrings which mention them in my notes.
Be careful to include all full original substrings with enough context merged into one text per person listed.
* Input format: list of people names comma separated
* Output format: {}
* People:
  * {}
* My notes: {}
        """
        sublist_in_query = "\n  *".join(sublist)
        query_mentions_first_try = query_mentions.format(
            "a valid json map with key is persons name and value is all the concatenated text, "
            + "include everyone from the input",
            sublist_in_query,
            full_transcript,
        )
        raw_response = gpt_client.run_prompt(query_mentions_first_try)
        people = gpt_response_to_json(raw_response)
        # TODO: Post GPT-4 we might be just able to remove this
        # if people is None:
        #     print("WARNING: Could not get substring mentions for the provided folks")
        #     query_mentions_second_try = query_mentions.format(
        #         "a valid json map with key equal to persons name and where value"
        #         "is a string joined of all found mentions",
        #         sublist_in_query,
        #         full_transcript,
        #     )
        #     raw_response = gpt_client.run_prompt(query_mentions_second_try)
        #     # TODO(P2, quality): Maybe we should filter out short or one sentence transcripts,
        #     #   or names which are clearly not humans like "Other European similar organizations".
        #     people = gpt_response_to_json(raw_response)
        #     # TODO: Some error handling and defaulting to retry one-by-one? I can see it a recurring theme
        #     #   of batch gpt failing and retrying with one-by-one.
        if len(people) != len(sublist):
            print(
                f"WARNING: mentions size {len(people)} different from input size {len(sublist)}"
            )
        # Update the existing map with the new entries
        result.update(people)

    return result


# TODO(P1, features): Dynamic summary categories based off:
#   * Background of the speaker: https://www.reversecontact.com/case-studies
#   * General question / note categories (chat-gpt)
#   * Static list to fill-in if not enough (get top 5 say).
#   * The above 3 lists consolidate with GPT.
#   NOTE: This also needs more templates.
summary_fields_preset = {
    "role": "current role or latest job experience",
    "industry": "which business area they specialize in professionally",
    "impressions": "my first impression of them summarized into one sentence",
    "their_needs": "list of what the person is looking for, null for empty",
    "my_takeaways": "list of my learnings, action items which should stay private to me",
    # Will need to improve this by better classification of the note
    "items_to_follow_up": (
        "list of items i explicitly mention which need my response to the person, "
        "ignore items which are already in my_takeaways, null if no items"
    ),
    "suggested_revisit": "priority of when should i respond to them, PO(today), P1(end of week), P2(later)",
}


def summarize_note_to_person_data_entry(
    gpt_client: OpenAiClient, name: str, note: str
) -> Optional[PersonDataEntry]:
    query_summarize = """
I want to structure the following note about {}
into a single json dictionary with the following key value pairs: {}

Output only the json dictionary.
My notes: {}"""
    person = PersonDataEntry()
    person.name = name
    person.transcript = note
    print(f"Getting a summary for {person.name}")
    # NOTE: transcript might be a list of strings.
    len_transcript = len(str(note))
    if len_transcript < MIN_TRANSCRIPT_LENGTH:
        print(
            f"Skipping summary for {name} as transcript too short: {len_transcript} < {MIN_TRANSCRIPT_LENGTH}"
        )
        raw_summary = None
        raw_response = f"Thanks for mentioning {name}! Unfortunately there is too little info to summarize from."
    else:
        # TODO(P1, bug): ParsingError: { "name": "Michmucho", "industry": "", "role": "", "vibes": "Unknown",
        #  "priority": 3, "follow_ups": null, "needs": null }
        raw_response = gpt_client.run_prompt(
            query_summarize.format(name, json.dumps(summary_fields_preset), note),
            print_prompt=True,
        )
        raw_summary = gpt_response_to_json(raw_response)

    if raw_summary is None:
        print(f"ERROR: Could NOT parse summary for {name}, defaulting to hand-crafted")
        person.batch_into_one_email = True
        person.parsing_error = raw_response
        return person

    # person.mnemonic = raw_summary.get("mnemonic", None)
    # person.mnemonic_explanation = raw_summary.get("mnemonic_explanation", None)
    person.batch_into_one_email = False  # TODO: Revisit this logic
    person.role = raw_summary.get("role", person.role)
    person.industry = raw_summary.get("industry", person.industry)
    person.impressions = raw_summary.get("impressions", person.impressions)
    person.their_needs = raw_summary.get("their_needs", person.their_needs)
    person.my_takeaways = raw_summary.get("my_takeaways", person.my_takeaways)
    person.items_to_follow_up = raw_summary.get(
        "items_to_follow_up", person.items_to_follow_up
    )
    person.suggested_revisit = raw_summary.get(
        "suggested_revisit", person.suggested_revisit
    )
    # TODO(P1, ux): Custom fields like their children names, or responses to recurring questions from me.
    # person.additional_metadata = {}
    return person


def generate_draft(gpt_client: OpenAiClient, person: PersonDataEntry) -> Optional[str]:
    print(f"generate_draft for {person}")
    # TODO(P0, ux): From the initial transcript we can get people I talked with (we currently do "people mentioned").
    # default_items_to_follow_up = ["To say: great to meet you, let me know if I can ever do anything for you!"]
    default_items_to_follow_up = []
    if person.items_to_follow_up is None:
        # TODO(P1, feature): Items will become sub-tasks for AUTO-GPT like features
        items = default_items_to_follow_up
    elif isinstance(person.items_to_follow_up, list):
        if len(person.items_to_follow_up) == 0:
            items = default_items_to_follow_up
        else:
            items = person.items_to_follow_up
    else:
        print(
            f"WARNING: Unexpected items type {type(person.items_to_follow_up)} for {person.name}"
        )
        items = [str(person.items_to_follow_up)]

    if len(items) == 0:
        print(f"NOTE: Nothing to draft for person {person.name}")
        return None
    items_str = "\n* ".join(items)

    # TODO(P1): Personalize the messages to my overall transcript vibes (here its more per-note).
    message_type = "email"
    style = "casual witty professional person"
    prompt_drafts = """
Being my personal executive assistant,
based on my attached notes,
please draft a brief {message_type} to {name} written in style of
a "{style}", adjusted to the talking style from my note.
Keep it on topic, without too many superlatives.

These are items to address in the {message_type}:
* {items_str}

Please make sure that:
* to mention what I enjoyed OR appreciated in the conversation
* include a fact / a hobby / an interest from our conversation
* omit, i.e. do not include any sensitive information like money
* only use facts provided in the note, don't make up things

My note {note}""".format(
        message_type=message_type,
        name=person.name,
        style=style,
        items_str=items_str,
        note=person.transcript,
    )
    raw_response = gpt_client.run_prompt(prompt_drafts)

    is_it_json = gpt_response_to_json(raw_response, debug=False)
    if isinstance(is_it_json, (dict, list)):
        print(f"WARNING: generate_draft returned a dict or list {raw_response}")
        raw_response = str(is_it_json)

    # TODO(P2, quality): We likely need to do more postprocessing here
    return raw_response


# =============== MAIN FUNCTIONS TO BE CALLED  =================
# Current approach is in two passes:
# * first is to extract all people the text talks about
# * second, for every person get all context which mentions or talks about them
# NOTE: The original approach of sub-stringing the original string worked only like 70% right (GPT3.5):
# * Many un-attributed gaps (which was painful to map)
# * Repeat mentions doesn't work
def run_executive_assistant_to_get_drafts(
    gpt_client: OpenAiClient, full_transcript: str
) -> List[PersonDataEntry]:
    token_count = num_tokens_from_string(full_transcript)
    print(f"extract_context_per_person on raw_transcript of {token_count} token count")

    people = named_entity_recognition(gpt_client, full_transcript)

    person_to_transcript = extract_context_per_person(
        gpt_client, full_transcript, people
    )
    # TODO(P1, quality): Make sure all of the original transcript is covered OR at least we should log it.
    print("=== All people with all their mentions === ")
    print(json.dumps(person_to_transcript))
    if person_to_transcript is None or len(person_to_transcript) == 0:
        return []

    person_data_entries: List[PersonDataEntry] = []
    for name, note in person_to_transcript.items():
        person_data_entry = summarize_note_to_person_data_entry(gpt_client, name, note)
        if person_data_entry is None:
            continue

        person_data_entry.next_draft = generate_draft(gpt_client, person_data_entry)
        person_data_entries.append(person_data_entry)

    print("=== All summaries === ")
    # Sort by priority, these are now P0, P1 so do it ascending.
    person_data_entries = sorted(person_data_entries, key=lambda pde: pde.sort_key())

    print(json.dumps([asdict(pde) for pde in person_data_entries]))
    return person_data_entries
