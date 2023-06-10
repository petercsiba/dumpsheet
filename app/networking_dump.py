import json
from dataclasses import asdict
from typing import Dict, List

import openai

from datashare import PersonDataEntry, Draft
from openai_client import gpt_response_to_json, gpt_response_to_plaintext, OpenAiClient
from storage_utils import get_fileinfo
from utils import Timer

MIN_TRANSCRIPT_LENGTH = 80  # characters, can prevent some "hallucinations"
MAX_TRANSCRIPT_TOKEN_COUNT = 2500  # words
test_transcript = None


# TODO(P0): Multi-language support (chinese, slovak), ideally we need to derive the language for transcript
#   * Use https://api.openai.com/v1/audio/translations
#   They support a shitload of languages.
#   NICE: Seems we can even run it locally
#     import whisper
#     model = whisper.load_model("large")
#     result = model.transcribe("recording.mp4", task='translate')
#     result['text']
#     And do it from public youtube videos with pytube
#       https://towardsdatascience.com/whisper-transcribe-translate-audio-files-with-human-level-performance-df044499877
# TODO(P1, devx): Maybe better place in openai_utils
def transcribe_audio(audio_filepath):
    if test_transcript is not None:
        return test_transcript

    prompt_hint = "these are notes from an event I attended describing the people I met, my impressions and actions"

    # (2023, May): File uploads are currently limited to 25 MB and the following input file types are supported:
    #   mp3, mp4, mpeg, mpga, m4a, wav, and webm
    # For longer inputs, we can use pydub to chunk it up
    #   https://platform.openai.com/docs/guides/speech-to-text/longer-inputs
    with open(audio_filepath, "rb") as audio_file:
        print(f"Transcribing {get_fileinfo(file_handle=audio_file)}")
        # Data submitted through the API is no longer used for service improvements (including model training)
        #   unless the organization opts in
        # https://openai.com/blog/introducing-chatgpt-and-whisper-apis
        with Timer("Audio transcribe"):
            transcript = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file,
                response_format="json",
                language="en",
                prompt=prompt_hint,
                # If set to 0, the model will use log probability to automatically increase the temperature
                #   until certain thresholds are hit.
                temperatue=0,
            )
            result = transcript["text"]
            print(f"Transcript: {result}")
            return result


# Current approach:
# * Do this in two passes, one is to get all people the text talks about
# * Then for every person get all substrings with any mention on them
# No dealing with indexes OR json messages here
# NOTE: The original approach of sub-stringing the original string worked only like 70% right:
# * Many un-attributed gaps (which was painful to map)
# * Repeat mentions doesn't work
# My mistake was that I tried to optimize token count, returning only indexes, which made the code very complicated.
def get_per_person_transcript(gpt_client: OpenAiClient, raw_transcript: str):
    transcript_words = raw_transcript.split()
    token_count = len(transcript_words)
    print(f"Transcript has {token_count} words")
    # Make sure to include the whole string without gaps.
    # TODO(P0, quality): Eventually we would need to implement this case
    if token_count > MAX_TRANSCRIPT_TOKEN_COUNT:
        print(f"ERROR: raw_transcript too long ({token_count}), truncating to {MAX_TRANSCRIPT_TOKEN_COUNT}")
        raw_transcript = " ".join(transcript_words[:MAX_TRANSCRIPT_TOKEN_COUNT])

    # TODO(P2, devx): Historically, this query give me most of the headaches.
    query_people = """ 
Find all the people mentioned in the follow note, please output a valid json list of strings 
where each string is a person name or identifier".
The transcript: {}
    """.format(raw_transcript)
    raw_response = gpt_client.run_prompt(query_people)
    people = gpt_response_to_json(raw_response)
    print(f"People: {json.dumps(people)}")

    # Solves TypeError: unhashable type: 'slice'
    if isinstance(people, dict):
        people = [f"{key}: {value}" for key, value in people.items()]
    elif isinstance(people, list):
        # Sometimes it's a list of dicts, so convert each person object to just a plain string.
        people = [gpt_response_to_plaintext(str(person)) for person in people]
    else:
        print(f"ERROR people response got un-expected type {type(people)}: {people}")

    result = {}
    size = 5
    sublists = [people[i:i+size] for i in range(0, len(people), size)]
    # Output format: json map of name to list of strings mentioning them
    # lead to non-parsaeble json like : ...cool",    ], (the extra comma)
    for sublist in sublists:
        query_mentions = """
For each of the follow people with their description, get all substrings which mention them in the transcript.
If they are referenced multiple times, make sure to include all full original substrings as a list of strings.
* Input format: json list of strings where each strings has format of name: super short characteristic
* Output format: {}
Try to use up all words from the transcript and include extra context for those substrings
* People: {}
* Transcript: {}
        """
        sublist_in_query = "\n*".join(sublist)
        query_mentions_first_try = query_mentions.format(
            "json map of name to list of substrings",
            sublist_in_query,
            raw_transcript
        )
        raw_response = gpt_client.run_prompt(query_mentions_first_try)
        people = gpt_response_to_json(raw_response)
        if people is None:
            print("WARNING: Could not get substring mentions for the provided folks")
            query_mentions_second_try = query_mentions.format(
                "json map with key equal to persons name and value as a string joined of all found mentions",
                sublist_in_query,
                raw_transcript
            )
            raw_response = gpt_client.run_prompt(query_mentions_second_try)
            # TODO(P2, quality): Maybe we should filter out short or one sentence transcripts,
            #   or names which are clearly not humans like "Other European similar organizations".
            people = gpt_response_to_json(raw_response)
            # TODO: Some error handling and defaulting to retry one-by-one? I can see it a recurring theme
            #   of batch gpt failing and retrying with one-by-one.
        if len(people) != len(sublist):
            print(f"WARNING: mentions size {len(people)} different from input size {len(sublist)}")
        # Update the existing map with the new entries
        result.update(people)

    # TODO(P1, devx): Here the transcript can be both a list of strings, or just a string.
    return result


# TODO: Assess what is a good amount of transcripts to send at the same time
#  .. well, cause matching the original raw transcript to the output of this, easiest seems to just do it one-by-one
#  I am paying by tokens so the overhead is the "function definition" (which we can fine-tune later on).
def summarize_transcripts_to_person_data_entries(
        gpt_client: OpenAiClient,
        person_to_transcript: Dict[str, str]
) -> List[PersonDataEntry]:
    # TODO(P0): Dynamic summary categories based off:
    #   * Background of the speaker: https://www.reversecontact.com/case-studies
    #   * General question / note categories (chat-gpt)
    #   * Static list to fill-in if not enough (get top 5 say).
    #   * The above 3 lists consolidate with GPT.
    #   NOTE: This also needs more templates.
    # Old stuff:
    # * contact_info: what channel we can contact like text, sms, linkedin, instagram and similar or null if none
    # TODO(P2, quality): Have GPT-4 rewrite prompts for GPT3.5 (did it for the mnemonic and that helped).
    query_summarize = """
I want to structure the following note describing me meeting {}.
Input: a transcript of me talking about the person.
Output: a single json dict with the following key value pairs:
    * name: name (or 2-3 word description) 
    * industry: which business area they specialize in professionally
    * role: current role or past experience
    * vibes: my first impression and general vibes of them
    * priority: on scale from 1 to 5 how excited i am to follow up, never null 
    * follow_ups: list of action items or follow ups i mentioned, null if none 
    * needs: list of their pain points, wants or blockers, null for empty
The input transcript: {}"""
    people = []
    for name, transcript in person_to_transcript.items():
        # Note: when I did "batch 20 structured summaries" it took 120 seconds.
        # Takes 10 second per person.
        print(f"Getting a summary for {name}")
        # NOTE: transcript might be a list of strings.
        len_transcript = len(str(transcript))
        if len_transcript < MIN_TRANSCRIPT_LENGTH:
            print(f"Skipping summary for {name} as transcript too short: {len_transcript} < {MIN_TRANSCRIPT_LENGTH}")
            raw_summary = None
            raw_response = f"Thanks for mentioning {name}! Unfortunately there is too little info to summarize from."
        else:
            # TODO(P1, bug): ParsingError: { "name": "Michmucho", "industry": "", "role": "", "vibes": "Unknown", "priority": 3, "follow_ups": null, "needs": null }
            raw_response = gpt_client.run_prompt(query_summarize.format(name, transcript), print_prompt=True)
            raw_summary = gpt_response_to_json(raw_response)

        person = PersonDataEntry()
        people.append(person)

        # NOTE: Here we update the name from the original derived one
        person.name = name
        person.transcript = transcript
        if raw_summary is None:
            print(f"Could NOT parse summary for {name}, defaulting to hand-crafted")
            person.priority = PersonDataEntry.PRIORITIES_MAPPING.get(1)
            person.parsing_error = raw_response
            continue

        summary_name = raw_summary.get("name", name)
        if summary_name != name:
            print(f"INFO: name from person chunking {name} ain't equal the one from the summary {summary_name}")

        person.priority = PersonDataEntry.PRIORITIES_MAPPING.get(raw_summary.get("priority", 2))
        # person.mnemonic = raw_summary.get("mnemonic", None)
        # person.mnemonic_explanation = raw_summary.get("mnemonic_explanation", None)
        person.industry = raw_summary.get("industry", None)
        person.vibes = raw_summary.get("vibes", "unknown")
        person.role = raw_summary.get("role", None)
        person.follow_ups = raw_summary.get("follow_ups", [])
        person.needs = raw_summary.get("needs", [])
        # TODO(P1, ux): Custom fields like their children names, or responses to recurring questions from me.
        person.additional_metadata = {}

        # Unfortunately, GPT 3.5 is not as good with creative work resulting into structured output
        # So making a separate query for the mnemonic
        query_mnemonic = (
            "I need your help with a fun little task. "
            f"Can you come up with a catchy three-word phrase that's easy to remember and includes {person.name}? " 
            "Here's the catch: all the words should start with the same letter and describe the person."
            "Please output the result on two lines as:\n"
            "* phrase\n"
            "* explanation of it in max 25 words\n"
            f"My notes: {person.transcript}"
        )
        raw_mnemonic = gpt_client.run_prompt(query_mnemonic, print_prompt=True)
        non_whitespace_lines = []
        if bool(raw_mnemonic):
            lines = str(raw_mnemonic).split("\n")
            non_whitespace_lines = [line for line in lines if line.strip() != '']
            if len(non_whitespace_lines) > 0:
                person.mnemonic = non_whitespace_lines[0]
            if len(non_whitespace_lines) > 1:
                person.mnemonic_explanation = non_whitespace_lines[1]
        if len(non_whitespace_lines) < 2:
            print(f"WARNING: Could NOT get mnemonic (catch phrase) for {person.name} got raw: {raw_mnemonic}")

    # TODO(P1, quality): There are too many un-named people, either:
    #  * Filter out transcripts which are a strict subset of other transcripts
    #  * Just filter out un-named person
    # So if GPT cannot name / identify the person, it's most likely a duplicate.
    likely_duplicate = ["unknown", "unnamed", "un-named", "unidentified"]
    filtered_result = []
    for person in people:
        if any(pattern.lower() in person.name.lower() for pattern in likely_duplicate):
            print(f"WARNING: Filtering out un-identified person {person.name} for transcript {person.transcript}")
            continue
        filtered_result.append(person)

    return filtered_result


def generate_first_outreaches(
        gpt_client: OpenAiClient,
        name: str,
        person_transcript: str,
        intents: List[str]
) -> List[Draft]:
    result = []
    for intent in intents:
        # TODO(P1): Personalize the messages to my general transcript vibes.
        # TODO(P2, feature): Add a text area which allows to fine-tune, regenerate the draft with extra prompts
        #   i.e. have an embedded chat gpt experience.
        #   Maybe add info from stalking tools like https://www.reversecontact.com
        query_outreaches = """ 
From the notes on the following person I just met at an event 
please generate a short outreach message written in style of 
a "smooth casual friendly yet professional person", 
ideally adjusted to the talking style from the note, 
to say that "{}"  (use up to 250 characters)
Please make sure that:
* to mention what I enjoyed OR appreciated in the conversation
* include a fact / a hobby / an interest from our conversation
* omit any sensitive information, especially money
Only output the resulting message - do not use double quotes at all.
My notes of person "{}" are as follows "{}" """.format(intent, name, person_transcript)
        raw_response = gpt_client.run_prompt(query_outreaches)

        is_it_json = gpt_response_to_json(raw_response, debug=False)
        if isinstance(is_it_json, (dict, list)):
            print(f"WARNING: generate_first_outreaches returned a dict or list {raw_response}")
            raw_response = str(is_it_json)

        result.append(Draft(
            intent=intent,
            message=raw_response
        ))

    return result


# =============== MAIN FUNCTIONS TO BE CALLED  =================
def extract_per_person_summaries(gpt_client: OpenAiClient, raw_transcript: str) -> List[PersonDataEntry]:
    print(f"Running networking_dump on raw_transcript of {len(raw_transcript.split())} token size")

    person_to_transcript = get_per_person_transcript(gpt_client, raw_transcript=raw_transcript)
    # TODO(P1, quality): Make sure all of the original transcript is covered OR at least we should log it.
    print("=== All people with all their mentions === ")
    print(json.dumps(person_to_transcript))

    person_data_entries = summarize_transcripts_to_person_data_entries(gpt_client, person_to_transcript)
    print("=== All summaries === ")
    # Sort by priority, these are now P0, P1 so do it ascending.
    person_data_entries = sorted(person_data_entries, key=lambda pde: pde.priority)

    print(json.dumps([asdict(pde) for pde in person_data_entries]))

    return person_data_entries


def fill_in_draft_outreaches(gpt_client: OpenAiClient, person_data_entries: List[PersonDataEntry]):
    print(f"Running fill_in_draft_outreaches on {len(person_data_entries)} person data entries")

    for person in person_data_entries:
        required_follow_ups = person.follow_ups or []
        intents = required_follow_ups.copy()

        # TODO(P1, cx): Here we should again use the 3-way approach for sub-prompts:
        #   * To parsed and static list, also add GPT gather general action items across people
        intents.extend([
            # Given data / intent of the networking person
            "Great to meet you, let me know if I can ever do anything for you!",
            "I want to meet again with one or two topics to discuss",
            "Appreciate meeting them at the event",
        ])
        top3_intents = intents[:max(3, len(required_follow_ups))]

        if person.parsing_error is not None and len(person.parsing_error) > 10:
            print(f"WARNING: Person {person.name} encountered a parsing error, shortening intents")
            # Likely means the transcript was odd, so don't even try much.
            top3_intents = ["Great to meet you, let me know if I can ever do anything for you!"]

        print(f"top3_intents {top3_intents}")

        person.drafts = generate_first_outreaches(
            gpt_client=gpt_client,
            name=person.name,
            person_transcript=person.transcript,
            intents=top3_intents
        )
