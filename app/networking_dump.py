import json
import openai
import pprint

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
def per_person_transcripts_to_summaries(person_to_transcript):
    # TODO(P0): Dynamic summary categories based off:
    #   * Background of the speaker: https://www.reversecontact.com/case-studies
    #   * General question / note categories (chat-gpt)
    #   * Static list to fill-in if not enough (get top 5 say).
    #   * The above 3 lists consolidate with GPT.
    #   NOTE: This also needs more templates.
    query_summarize = """
        I want to structure the following note describing me meeting a person.
        Input: a transcript of me talking about the person.
        Output: a json dict with the following key value pairs:
    * name: name (or 2-3 word description)
    * role: current role or past experience 
    * industry: one two works for the are of their specialty, or null if not sure
    * vibes: my first impression and general vibes of them
    * priority: on scale from 1 to 5 how excited i am to follow up, never null 
    * needs: list of what they are looking for soon or right now, null for empty
    * contact_info: what channel we can contact like text, sms, linkedin, instagram and similar or null if none
    * follow_ups: list of action items or follow ups i mentioned, null if none 
    The input transcript: {}"""
    if test_summaries is not None:
        summaries = gpt_response_to_json(test_summaries)
    else:
        summaries = []
        for name, transcript in person_to_transcript.items():
            # Note: when I did "batch 20 structured summaries" it took 120 seconds.
            # Takes 10 second per person.
            print(f"Getting all mentions for {name}")
            # TODO: We might need to go back to the original slicing? Or at least somehow attribute the missing parts
            raw_response = run_prompt(query_summarize.format(transcript), print_prompt=True)
            # One failure shouldn't block the entire thing, log the error, return name, transcript for manual fix.
            summary = gpt_response_to_json(raw_response)
            # TODO(P1): Handle this error case:
            # Sorry, there is no information in the input transcript to structure a note describing a person
            if summary is None:
                print(f"Could NOT parse summary for {name}, defaulting to hand-crafted")
                summary = {
                    "role": None,
                    "industry": None,
                    "vibes": None,
                    "priority": 2,
                    "needs": None,
                    "contact_info": None,
                    "follow_ups": [],
                    "error": raw_response,
                }
            summary["name"] = name
            summary["transcript"] = transcript
            summary["error"] = None
            summaries.append(summary)

    return summaries


# TODO(P1): Rename the entire pipeline to drafts and topics.
def generate_first_outreaches(name, person_transcript, intents):
    # TODO(P2): Try adding context on the person who inputs the transcripts, mid-term can be automated with
    #   tools like https://www.reversecontact.com
    result = []
    for intent in intents:
        # TODO(P2): The problem with individual queries are more frequent rate limits :/
        #   Well, have to find a way to parse a general "list" response from GPT (without using GPT)
        # Note: Didn't work: I am venture capitalist from czech republic.
        # Note: tried to do it in batch and parsing the JSON output, but GPT isn't the most consistent
        # about it. For future rather run more tokens / queries then trying to batch it (for now).
        # TODO(P0, vertical-saas): We should improve generalize these
        # TODO(P0, fine-tune): Add a text area which allows to fine-tune, regenerate the draft with extra prompts
        #   i.e. have an embedded chat gpt experience
        # TODO(P1): Personalize the messages to my general transcript vibes.
        query_outreaches = """ 
        From the notes on the following person I met at an event 
        please generate short outreach message writing as a smooth casual friendly yet professional talker 
        to say "{}"  (up to 250 characters)
        Make sure that:
        * saying that I enjoyed OR appreciated in the conversation
        * include a fact from our conversation
        * reflect my note-taking style into the generated text
        Only output the resulting message - do not use double quotes at all.
        My notes of person {} are as follows {}
        """.format(intent, name, person_transcript)
        raw_response = run_prompt(query_outreaches)
        result.append({
            "name": name,  # used to join on the summaries
            "message_type": intent,
            "outreach_draft": raw_response,
        })
    # pp.pprint(result)
    return result


# =============== MAIN FUNCTIONS TO BE CALLED  =================
def extract_per_person_summaries(raw_transcript: str):
    print(f"Running networking_dump on raw_transcript of {len(raw_transcript.split())} token size")

    if test_person_to_transcript is None:
        person_to_transcript = get_per_person_transcript(raw_transcript=raw_transcript)
    else:
        person_to_transcript = gpt_response_to_json(test_person_to_transcript)
    # TODO: Somehow get all "gaps" none of the mentions is talking about.
    print("=== All people with all their mentions === ")
    print(json.dumps(person_to_transcript))

    if test_summaries is not None:
        summaries = gpt_response_to_json(test_summaries)
    else:
        summaries = per_person_transcripts_to_summaries(person_to_transcript)
    print("=== All summaries === ")
    summaries = sorted(summaries, key=lambda x: x.get('priority', 2), reverse=True)
    # Katka really wants text priorities
    for i, person in enumerate(summaries):
        priorities_mapping = {
            5: "P0 - DO IT ASAP!",
            4: "P1 - High: This is important & needed",
            3: "P2 - Medium: Nice to have",
            2: "P3 - Unsure: Check if you have time",
            1: "P4 - Low: Just don't bother",
        }
        summaries[i]["priority"] = priorities_mapping.get(person.get("priority", 2))

    print(json.dumps(summaries))

    return summaries


def generate_draft_outreaches(summaries):
    print(f"Running generate_draft_outreaches on {len(summaries)} summaries")
    # Priority 5 is the highest, 1 is lowest
    drafts = []
    for person in summaries:
        if person is None:
            print("skipping None person from summaries")
            continue
        drafts_for = []
        mentioned_follow_ups = person.get("follow_ups", None)
        mentioned_follow_ups = [] if mentioned_follow_ups is None else mentioned_follow_ups
        for follow_up in mentioned_follow_ups:
            drafts_for.append(f"to follow up on {follow_up}")
        # TODO(P0): Here we should again use the 3-way approach for sub-prompts:
        #   * GPT gather general action items across people
        #   * Parse per-person
        #   * Use a static list
        #   AND pick the 3 most relevant (long-term using embeddings).
        drafts_for.extend([
            # Given data / intent of the networking person
            "appreciate meeting them at the event",
            "great to meet you, let me know if I can ever do anything for you!",
            "I want to meet again with one or two topics to discuss",
        ])
        # TODO(P1, small): Draft a thank you note to the event host.

        outreaches = generate_first_outreaches(
            person["name"],
            person_transcript=person.get("transcript"),
            intents=drafts_for
        )
        drafts.extend(outreaches)

    print("=== All drafts dumped === ")
    print(json.dumps(drafts))
    return drafts
