import json
from typing import Dict, List, Optional

from app.datashare import PersonDataEntry
from app.form_library import get_form
from common.form import FormName
from gpt_form_filler.openai_client import (
    DEFAULT_MODEL,
    OpenAiClient,
    gpt_response_to_json,
    num_tokens_from_string,
)

# Min transcript size somewhat trims down on "hallucinations"
MIN_FULL_TRANSCRIPT_CHAR_LENGTH = 100
MIN_FULL_TRANSCRIPT_CHAR_LENGTH_TO_GENERATE_SUMMARY = 200
MIN_PERSON_TRANSCRIPT_CHAR_LENGTH = 140
MAX_TRANSCRIPT_TOKEN_COUNT = 2500  # words


# TODO(P1, devx): Historically, this query give me most of the headaches.
#   * GPT-4 suggests using Named Entity Recognition (NER) - with nodes and edges.
#   * If it remains a problem - maybe just do it one-by-one, screw token cost.
# TODO(P0, ux): This can drop information, e.g. we can mention talking about SHACK15 and it wouldn't be included.
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
    people = gpt_response_to_json(raw_response)
    if people is not None and not isinstance(people, list):
        print(f"ERROR: Could NOT parse people into LIST from raw_response {raw_response}")
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


def summarize_note(gpt_client: OpenAiClient, raw_note: str):
    return gpt_client.run_prompt(
        f"""Summarize my following meeting note into a short concise structured output,
        make sure to include all facts, if needed label those facts
        so I can review this in a year and know what happened.
        Only output the result.
        My raw notes: {raw_note}
        """
    )


def summarize_raw_note_to_person_data_entry(
    gpt_client: OpenAiClient, name: str, raw_note: str
) -> Optional[PersonDataEntry]:
    person = PersonDataEntry()
    person.name = name
    person.transcript = raw_note
    print(f"Getting a summary for {person.name}")
    # NOTE: transcript might be a list of strings.
    len_transcript = len(str(raw_note))
    if len_transcript < MIN_PERSON_TRANSCRIPT_CHAR_LENGTH:
        print(
            f"Skipping summary for {name} as transcript too short: "
            f"{len_transcript} < {MIN_PERSON_TRANSCRIPT_CHAR_LENGTH}"
        )
        form_data = None
        err = f"Thanks for mentioning {name}! Unfortunately there is too little info to summarize from."
    else:
        form_data, err = gpt_client.fill_in_form(
            form=get_form(form_name=FormName.CONTACTS),
            text=raw_note,
            print_prompt=True,
        )

    if form_data is None:
        print(f"ERROR: Could NOT parse summary for {name}, defaulting to hand-crafted")
        person.batch_into_one_email = True
        person.parsing_error = err
        return person

    # person.mnemonic = form_data.get_value("mnemonic", None)
    # person.mnemonic_explanation = form_data.get_value("mnemonic_explanation", None)
    # NOTE: Yeah, we should get rid of PersonDataEntry in favor of the FormData, but this refactor is already too big.
    person.role = form_data.get_value("role", person.role)
    person.industry = form_data.get_value("industry", person.industry)
    person.key_facts = form_data.get_value("key_facts", person.key_facts)
    person.my_action_items = form_data.get_value(
        "my_action_items", person.my_action_items
    )
    person.suggested_response_item = form_data.get_value(
        "suggested_response_item", person.suggested_response_item
    )
    person.response_message_type = form_data.get_value("response_message_type")
    person.their_needs = form_data.get_value("their_needs", person.their_needs)
    person.suggested_revisit = form_data.get_value(
        "suggested_revisit", person.suggested_revisit
    )
    person.summarized_note = (
        raw_note
        if len(raw_note) < MIN_FULL_TRANSCRIPT_CHAR_LENGTH_TO_GENERATE_SUMMARY
        else summarize_note(gpt_client, raw_note)
    )
    form_data.set_field_value("name", name)
    form_data.set_field_value("summarized_note", person.summarized_note)
    person.form_data = form_data
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
        "email": "400 characters easy-to-read email to the point; as a casual, calm, friendly executive person",
        "linkedin": "300 characters linkedin outreach no bullshit; as a casual, calm, friendly, professional person",
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
please draft a up to {template} to {name} i met as a response to address {response_item}
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
# TODO(P0, devx): Add task_id to the networking pipeline
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
    for name, raw_note in person_to_transcript.items():
        person_data_entry = summarize_raw_note_to_person_data_entry(
            gpt_client, name, raw_note
        )
        if person_data_entry is None:
            continue

        if person_data_entry.should_draft():
            person_data_entry.next_draft = generate_draft(gpt_client, person_data_entry)
            person_data_entry.form_data.set_field_value(
                "next_draft", person_data_entry.next_draft
            )

        person_data_entries.append(person_data_entry)

    print("=== All summaries === ")
    # Sort by priority, these are now P0, P1 so do it ascending.
    person_data_entries = sorted(person_data_entries, key=lambda pde: pde.sort_key())
    return person_data_entries
