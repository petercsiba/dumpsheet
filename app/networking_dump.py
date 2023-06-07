import json
from typing import Dict, List

import openai
import pprint

from app.datashare import PersonDataEntry
from openai_utils import gpt_response_to_json, gpt_response_to_plaintext, run_prompt, Timer
from storage_utils import get_fileinfo

MAX_TRANSCRIPT_TOKEN_COUNT = 2500

# config = toml.load('secrets.toml')
# TODO: Change after some time - I am lazy to remove from commits or do ENV variables :D
openai.api_key = "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"
# AUDIO_FILE = "input/networking-transcript-1-katka-tech-roast-may-25.mp4"
# command = f"ffmpeg -i input/{AUDIO_FILE} -c:v copy -c:a aac -strict experimental"
# result = subprocess.run(command, shell=True, capture_output=True, text=True)
# TODO: Time for local and production settings
# output_bucket = None
output_bucket = "katka-email-response"

pp = pprint.PrettyPrinter(indent=4)

test_transcript = None
test_get_names = None
test_person_to_transcript = None
test_summaries = None


# TODO: Maybe better place in openai_utils
# TODO(P2): Multi-language support (chinese, slovak), ideally we need to derive the language for transcript
#   * https://platform.openai.com/docs/api-reference/audio
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
def get_per_person_transcript(raw_transcript: str):
    transcript_words = raw_transcript.split()
    token_count = len(transcript_words)
    print(f"Transcript has {token_count} words")
    # Make sure to include the whole string without gaps.
    # TODO: Eventually we would need to implement this case
    if token_count > MAX_TRANSCRIPT_TOKEN_COUNT:
        print(f"ERROR: raw_transcript too long ({token_count}), truncating to {MAX_TRANSCRIPT_TOKEN_COUNT}")
        raw_transcript = " ".join(transcript_words[:MAX_TRANSCRIPT_TOKEN_COUNT])

    query_people = """ 
    Enumerate all people mentioned in the attached transcript, 
    please output a valid json list of strings in format: 
    * "person identifier (such as name): a 5-10 word description".
    Note that: 
    * There might be many un-named people, make sure to include them all.
    * If two people without name sound similar then they are the same.
    * If the pronoun he, she, them or it changes, these are likely different people. 
    The transcript: {}
    """.format(raw_transcript)
    if test_get_names is None:
        raw_response = run_prompt(query_people)
        people = gpt_response_to_json(raw_response)
    else:
        people = gpt_response_to_json(test_get_names)
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
    # TODO: Handle people null case
    sublists = [people[i:i+size] for i in range(0, len(people), size)]
    # Output format: json map of name to list of strings mentioning them
    # lead to non-parsaeble json like : ...cool",    ], (the extra comma)
    for sublist in sublists:
        # TODO: Try using the Chat API to re-use the same input transcript
        #   Might be NOT possible cause it takes a list of messages
        query_mentions = """
        For each of the follow people with their description, get all substrings which mention them in the transcript.
        If they are referenced multiple times, make sure to include all full original substrings as a list of strings.
        Input format: json list of strings where each strings has format of name: super short characteristic
        Output format: {}
        Try to use up all words from the transcript and include extra context for those substrings
        People: {}
        Transcript: {}
        """
        sublist_in_query = "\n*".join(sublist)
        query_mentions_first_try = query_mentions.format(
            "json map of name to list of substrings",
            sublist_in_query,
            raw_transcript
        )
        raw_response = run_prompt(query_mentions_first_try)
        people = gpt_response_to_json(raw_response)
        if people is None:
            print("WARNING: Could not get substring mentions for the provided folks")
            query_mentions_second_try = query_mentions.format(
                "json map with key equal to persons name and value as a string joined of all found mentions",
                sublist_in_query,
                raw_transcript
            )
            raw_response = run_prompt(query_mentions_second_try)
            people = gpt_response_to_json(raw_response)
            # TODO: Some error handling and defaulting to retry one-by-one? I can see it a recurring theme
            #   of batch gpt failing and retrying with one-by-one.
        if len(people) != len(sublist):
            print(f"WARNING: mentions size {len(people)} different from input size {len(sublist)}")
        # Update the existing map with the new entries
        result.update(people)

    return result


# TODO: Assess what is a good amount of transcripts to send at the same time
#  .. well, cause matching the original raw transcript to the output of this, easiest seems to just do it one-by-one
#  I am paying by tokens so the overhead is the "function definition" (which we can fine-tune later on).
def summarize_transcripts_to_person_data_entries(person_to_transcript: Dict[str, str]) -> List[PersonDataEntry]:
    # TODO(P0): Dynamic summary categories based off:
    #   * Background of the speaker: https://www.reversecontact.com/case-studies
    #   * General question / note categories (chat-gpt)
    #   * Static list to fill-in if not enough (get top 5 say).
    #   * The above 3 lists consolidate with GPT.
    #   NOTE: This also needs more templates.
    # Old stuff:
    # * contact_info: what channel we can contact like text, sms, linkedin, instagram and similar or null if none
    query_summarize = """
        I want to structure the following note describing me meeting a person.
        Input: a transcript of me talking about the person.
        Output: a json dict with the following key value pairs:
    * name: name (or 2-3 word description) 
    * mnemonic: two word mnemonic to remember this person, both words starting with the same letter as their name
    * mnemonic_explanation: include a short explanation for the above mnemonic
    * industry: which business area they specialize in professionally
    * role: current role or past experience
    * vibes: my first impression and general vibes of them
    * priority: on scale from 1 to 5 how excited i am to follow up, never null 
    * follow_ups: list of action items or follow ups i mentioned, null if none 
    * needs: list of their pain points, wants or blockers, null for empty
    The input transcript: {}"""
    if test_summaries is not None:
        # TODO(P2, testing): We now return PersonDataEntry instead of JSON so this won't work. Maybe cleanup.
        result = gpt_response_to_json(test_summaries)
    else:
        result = []
        for name, transcript in person_to_transcript.items():
            # Note: when I did "batch 20 structured summaries" it took 120 seconds.
            # Takes 10 second per person.
            print(f"Getting all mentions for {name}")
            raw_response = run_prompt(query_summarize.format(transcript), print_prompt=True)
            # One failure shouldn't block the entire thing, log the error, return name, transcript for manual fix.
            # TODO(P1): Handle this error case:
            #   For inputs like The input transcript: ['The Riga, there was one moderator']
            #   Sorry, there is no information in the input transcript to structure a note describing a person
            #   Sorry, the input transcript is too short to extract any meaningful information about a person I met.
            #       Please provide a longer transcript with more details about the person
            raw_summary = gpt_response_to_json(raw_response)

            person = PersonDataEntry()
            result.append(person)
            if raw_summary is None:
                print(f"Could NOT parse summary for {name}, defaulting to hand-crafted")
                person.parsing_error = raw_response
                continue

            summary_name = raw_summary.get("name", name)
            if summary_name != name:
                print(f"INFO: name from person chunking {name} ain't equal the one from the summary {summary_name}")

            person.name = name
            person.transcript = transcript
            person.priority = PersonDataEntry.PRIORITIES_MAPPING.get(raw_summary.get("priority", 2))
            person.mnemonic = raw_summary.get("mnemonic", None)
            person.mnemonic_explanation = raw_summary.get("mnemonic_explanation", None)
            person.industry = raw_summary.get("industry", None)
            person.vibes = raw_summary.get("vibes", "unknown")
            person.role = raw_summary.get("role", None)
            person.follow_ups = raw_summary.get("follow_ups", [])
            person.needs = raw_summary.get("needs", [])
            # TODO(P1, ux): Custom fields like their children names, or responses to recurring questions from me.
            person.additional_metadata = {}

    return result


def generate_first_outreaches(name: str, person_transcript: str, intents: List[str]) -> List[Dict[str, str]]:
    result = []
    for intent in intents:
        # TODO(P1): Personalize the messages to my general transcript vibes.
        # TODO(P2, feature): Add a text area which allows to fine-tune, regenerate the draft with extra prompts
        #   i.e. have an embedded chat gpt experience.
        #   Maybe add info from stalking tools like https://www.reversecontact.com
        query_outreaches = """ 
        From the notes on the following person I met at an event 
        please generate a short outreach message written in style of 
        a "smooth casual friendly yet professional person", ideally adjusted to the talking style from the note, 
        to say that "{}"  (use up to 250 characters)
        Please make sure that:
        * to mention what I enjoyed OR appreciated in the conversation
        * include a fact from our conversation
        Only output the resulting message - do not use double quotes at all.
        My notes of person "{}" are as follows "{}"
        """.format(intent, name, person_transcript)
        raw_response = run_prompt(query_outreaches)

        is_it_json = gpt_response_to_json(raw_response, debug=False)
        if isinstance(is_it_json, (dict, list)):
            print(f"WARNING: generate_first_outreaches returned a dict or list {raw_response}")
            raw_response = str(is_it_json)

        result.append({
            "message_type": intent,
            "outreach_draft": raw_response,
        })

    return result


# =============== MAIN FUNCTIONS TO BE CALLED  =================
def extract_per_person_summaries(raw_transcript: str) -> List[PersonDataEntry]:
    print(f"Running networking_dump on raw_transcript of {len(raw_transcript.split())} token size")

    if test_person_to_transcript is None:
        person_to_transcript = get_per_person_transcript(raw_transcript=raw_transcript)
    else:
        person_to_transcript = gpt_response_to_json(test_person_to_transcript)
    # TODO: Somehow get all "gaps" none of the mentions is talking about.
    print("=== All people with all their mentions === ")
    print(json.dumps(person_to_transcript))

    if test_summaries is not None:
        # TODO(P2, testing): Fix this, we might just do GPT-request caching through openai_utils.py via DynamoDB
        person_data_entries = gpt_response_to_json(test_summaries)
    else:
        person_data_entries = summarize_transcripts_to_person_data_entries(person_to_transcript)
    print("=== All summaries === ")
    # Sort by priority, these are now P0, P1 so do it ascending.
    person_data_entries = sorted(person_data_entries, key=lambda pde: pde.priority)

    print(json.dumps(person_data_entries))

    return person_data_entries


def fill_in_draft_outreaches(person_data_entries: List[PersonDataEntry]):
    print(f"Running generate_draft_outreaches on {len(person_data_entries)} person data entries")

    for person in person_data_entries:
        required_follow_ups = person.follow_ups or []
        intents = required_follow_ups.copy()

        # TODO(P1, cx): Here we should again use the 3-way approach for sub-prompts:
        #   * To parsed and static list, also add GPT gather general action items across people
        intents.extend([
            # Given data / intent of the networking person
            "I want to meet again with one or two topics to discuss",
            "Great to meet you, let me know if I can ever do anything for you!",
            "Appreciate meeting them at the event",
        ])
        top3_intents = intents[:max(3, len(required_follow_ups))]

        person.drafts = generate_first_outreaches(
            person.name,
            person_transcript=person.transcript,
            intents=top3_intents
        )

