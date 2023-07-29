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

# Min transcript size somewhat trims down on "hallucinations"
MIN_FULL_TRANSCRIPT_CHAR_LENGTH = 100
MIN_PERSON_TRANSCRIPT_CHAR_LENGTH = 80
MAX_TRANSCRIPT_TOKEN_COUNT = 2500  # words


# TODO(P1, devx): Historically, this query give me most of the headaches.
#   * GPT-4 suggests using Named Entity Recognition (NER) - with nodes and edges.
#   * If it remains a problem - maybe just do it one-by-one, screw token cost.
def extract_everyone_i_have_talked_to(
    gpt_client: OpenAiClient, full_transcript: str
) -> List:
    # NOTE: We shorten the string by words cause easier, but we better estimate the token count by OpenAI counter.
    token_count = num_tokens_from_string(full_transcript)
    print(f"Transcript has {token_count} words and {len(full_transcript)} characters")

    # This can happen for either super-short, or silent uploads
    if len(full_transcript) < 5 or token_count <= 1:
        print("WARNING: Transcript too short")
        return []

    # Make sure to include the whole string without gaps.
    # TODO(P1, quality): Eventually we would need to implement processing a larger input (Claude, or split it up).
    if token_count > MAX_TRANSCRIPT_TOKEN_COUNT:
        print(
            f"ERROR: raw_transcript too long ({token_count}), truncating to {MAX_TRANSCRIPT_TOKEN_COUNT}"
        )
        transcript_words = full_transcript.split()
        full_transcript = " ".join(transcript_words[:MAX_TRANSCRIPT_TOKEN_COUNT])

    # TODO(P1, research): Understand if GPT function calling can help us. From first read it seems that the use case
    #   is for GPT to call other APIs. But they mention `extract_people_data` from a Wikipedia article
    # https://openai.com/blog/function-calling-and-other-api-updates
    # TODO(P0, ux): Still often-times it treats "Katka" and "Katka Sabo" as different people.
    query_people = """
    This is a voice note from a meeting or event where I talked to one or multiple people.
    List everybody I have directly talked to, omit mentions of other people in our conversation.
    Output a valid json list of strings of the people I have directly talked to
    - sometimes I don't recall their names so use a short description.
    Voice transcript of our meeting: {}
        """.format(
        full_transcript
    )
    raw_response = gpt_client.run_prompt(query_people)
    if raw_response is None:
        print("WARNING: Likely no people found in the input transcript")
        return []
    people = gpt_response_to_json_list(raw_response)
    print(f"==PEOPLE I TALKED TO: {json.dumps(people)}")
    return people


# Return a dict(name -> context)
# My mistake was that I tried to optimize token count, returning only indexes, which made the code very complicated.
def extract_context_per_person(
    gpt_client: OpenAiClient, full_transcript: str, people: List[str]
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
        # This is important to get right, so alert.
        if people is None:
            raise ValueError(
                f"couldn't parse people list from raw_response {raw_response}"
            )
        # if isinstance(people, list)
        if isinstance(people, dict):  # expected outcome
            for name, transcript in people.items():
                if transcript is None or len(str(transcript)) < 5:
                    print(
                        f"WARNING: extracted context for {name} is too short: {transcript}"
                    )

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
    "key_facts": "list of key facts each fact in a super-short up to 5 word brief, null for empty",
    "my_action_items": "list of action items I explicitly assigned myself to address after the meeting, null for empty",
    "suggested_response_item": (
        "one key topic or item for my follow up response to the person, "
        "default to 'great to meet you, let me know if I can ever do anything for you'"
    ),
    "response_message_type": "best message channel like email, sms, linkedin, whatsapp for me to respond on",
    "suggested_revisit": "priority of when should i respond to them, PO (today), P1 (end of week), P2 (later)",
}


def summarize_note_to_person_data_entry(
    gpt_client: OpenAiClient, name: str, note: str
) -> Optional[PersonDataEntry]:
    query_summarize = """
I want to structure the following note about {}
into a single json dictionary with the following key value pairs: {}
Keep it brief to the point.
Output only the resulting json dictionary.
My notes: {}"""
    person = PersonDataEntry()
    person.name = name
    person.transcript = note
    print(f"Getting a summary for {person.name}")
    # NOTE: transcript might be a list of strings.
    len_transcript = len(str(note))
    if len_transcript < MIN_PERSON_TRANSCRIPT_CHAR_LENGTH:
        print(
            f"Skipping summary for {name} as transcript too short: "
            f"{len_transcript} < {MIN_PERSON_TRANSCRIPT_CHAR_LENGTH}"
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
    # person.mnemonic_explanation = raw_summary.get("mnemonic_explanation", None)c
    person.role = raw_summary.get("role", person.role)
    person.industry = raw_summary.get("industry", person.industry)
    person.impressions = raw_summary.get("impressions", person.impressions)
    person.key_facts = raw_summary.get("key_facts", person.key_facts)
    person.my_action_items = raw_summary.get("my_action_items", person.my_action_items)
    person.suggested_response_item = raw_summary.get(
        "suggested_response_item", person.suggested_response_item
    )
    person.response_message_type = raw_summary.get("response_message_type")
    if person.response_message_type is None:
        person.response_message_type = "sms"
    person.response_message_type.lower()
    person.their_needs = raw_summary.get("their_needs", person.their_needs)
    person.suggested_revisit = raw_summary.get(
        "suggested_revisit", person.suggested_revisit
    )
    # TODO(P1, ux): Custom fields like their children names, or responses to recurring questions from me.
    # person.additional_metadata = {}
    return person


def generate_draft(gpt_client: OpenAiClient, person: PersonDataEntry) -> Optional[str]:
    # TODO(P1, feature): Eventually this function will get complicated at which point we should revisit
    print(f"generate_draft for {person.name}")
    if person.suggested_response_item is None:
        print(f"WARNING: no suggested response item for {person.name}")
        return None
    response_item = person.suggested_response_item

    # 41. 90% of leads are preferred to be texted, as compared to be called.
    # 42. In business, SMS response rates are 295% higher than the rates from the phone calls.
    message_type_to_template = {
        "email": "400 characters one paragraph email; as a casual, calm, friendly silicon valley executive",
        "linkedin": "300 characters one paragraph linkedin outreach; as a casual, calm, friendly, professional",
        "whatsapp": "200 characters sms message; as a friendly, to the point, yet professional person",
        "sms": "150 characters message; as a witty, to the point, friendly, yet professional person",
    }
    message_type = (
        person.response_message_type
        if person.response_message_type in message_type_to_template
        else "email"
    )
    template = message_type_to_template[message_type]

    # TODO(P1): Personalize the messages to my overall transcript vibes (here its more per-note).
    style = ""
    prompt_drafts = """
Being my personal executive assistant,
based on my attached notes,
please draft a {template} to {name} i met as a response to address {response_item}
written in style of a "{style}", adjusted to the talking style from my note.
Keep it on topic, tone it down.

Please make sure that:
* to mention one thing I have enjoyed OR appreciated in the conversation to show that i care
* include one fact from our conversation to show i that i am listening
* omit sensitive information like money
* do not use buzzwords or filler words like interesting, meaningful, intriguing

My note {note}""".format(
        template=template,
        name=person.name,
        response_item=response_item,
        style=style,
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
    if len(full_transcript) < MIN_FULL_TRANSCRIPT_CHAR_LENGTH:
        print(
            f"WARNING: full_transcript length too short {MIN_FULL_TRANSCRIPT_CHAR_LENGTH}"
        )

    token_count = num_tokens_from_string(full_transcript)
    print(f"extract_context_per_person on raw_transcript of {token_count} token count")

    people = extract_everyone_i_have_talked_to(gpt_client, full_transcript)
    if len(people) == 0:
        return []

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

        if person_data_entry.should_draft():
            person_data_entry.next_draft = generate_draft(gpt_client, person_data_entry)

        person_data_entries.append(person_data_entry)

    print("=== All summaries === ")
    # Sort by priority, these are now P0, P1 so do it ascending.
    person_data_entries = sorted(person_data_entries, key=lambda pde: pde.sort_key())

    print(
        json.dumps(
            [
                asdict(pde)
                for pde in person_data_entries
                if pde.should_show_full_contact_card()
            ]
        )
    )
    return person_data_entries
