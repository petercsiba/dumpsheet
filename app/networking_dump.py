import json
import openai
import os
import pprint

from openai_utils import gpt_response_to_json, run_prompt, Timer

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


# It can be that GPT returns different keys even running the same things
def multiget(arr, key1, key2):
    if key1 in arr:
        return arr[key1]
    return arr[key2]


def get_fileinfo(file_handle):
    file_size_bytes = os.path.getsize(file_handle.name)
    file_size_mb = file_size_bytes / (1024 * 1024)
    return f"File {file_handle.name} is {file_size_mb:.2f} MB"


def generate_transcript(audio_filepath, prompt_hint=None):
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
# * Then for everyone get all substrings with any mention on them
# No dealing with indexes OR json messages here
# NOTE: The original approach of sub-stringing the original string worked only like 70% right:
# * Many un-attributed gaps (which was painful to map)
# * Repeat mentions doesn't work
# My mistake was that I tried to optimize token count, returning only indexes, which made the code very complicated.
def get_per_person_transcript(raw_transcript):
    transcript_words = raw_transcript.split()
    token_count = len(transcript_words)
    print(f"Transcript has {token_count} words")
    # Make sure to include the whole string without gaps.
    assert(token_count < 3500)  # todo implement this case

    query_people = """ 
    Enumerate all persons the following transcript talks about, 
    formatted as a json list of strings in format name : 5 words describing them, 
    if two people without name sound similar then they are the same
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

    result = {}
    size = 5
    sublists = [people[i:i+size] for i in range(0, len(people), size)]
    # Output format: json map of name to list of strings mentioning them
    # lead to non-parsaeble json like : ...cool",    ], (the extra comma)
    for sublist in sublists:
        # TODO: Try using the Chat API to re-use the same input transcript
        #   Might be NOT possible cause it takes a list of messages
        query_mentions = """
        For each of the follow people, get all substrings which mention them from the transcript.
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
        # TODO: wtf WARNING: mentions size 2 different from input size 2
        if len(people) != len(sublists):
            print(f"WARNING: mentions size {len(people)} different from input size {len(sublist)}")
        # Update the existing map with the new entries
        result.update(people)

    return result


# TODO: Assess what is a good amount of transcripts to send at the same time
#  .. well, cause matching the original raw transcript to the output of this, easiest seems to just do it one-by-one
#  I am paying by tokens so the overhead is the "function definition" (which we can fine-tune later on).
def per_person_transcripts_to_summaries(person_to_transcript):
    # These we can derive later in the "keep your relationship warm" funnel.
    # * location: currently located at, or null if i don't mention it
    # * next_message_drafts: ideas of messages i can reach out with which have some value to them
    # * desires: what they want to achieve long-term, null for empty
    # * offers: list of skills they have, topics they understand or services they advertise, null for empty
    # TODO: Well, maybe it's better to just always include the full transcript when scraping for a person
    query_summarize = """
        I want to structure the following note describing me meeting a person.
        Input: a transcript of me talking about the person.
        Output: a json dict with the following key value pairs:
    * name: name
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


# Input is a dictionary of fields to values
# Output is list of candidate texts
def generate_first_outreaches(name, person_transcript, intents):
    result = []
    for intent in intents:
        # Historical note: tried to do it in batch and parsing the JSON output, but GPT isn't the most consistent
        # about it. For future rather run more tokens / queries then trying to batch it (for now).
        # TODO: The problem with individual queries are more frequent rate limits :/
        #   Well, have to find a way to parse a general "list" response from GPT (without using GPT)
        # Note: Didn't work:
        # I am venture capitalist from czech republic.
        query_outreaches = """ 
        For the following person I met at a networking event last night generate a short casual outreach message
        personalized to the facts of the person with the intent {}.
        Only output the resulting message - do not use double quotes.
        My knowledge of {} is {}
        """.format(intent, name, person_transcript)
        raw_response = run_prompt(query_outreaches)
        result.append({
            "name": name,
            "message_type": intent,
            "outreach_draft": raw_response,
        })
    # pp.pprint(result)
    return result


def networking_dump(audio_file):
    print(f"Running networking_dump on {audio_file}")
    if test_transcript is None:
        prompt_hint = "notes from a networking event about the new people I met with my impressions and follow up ideas"
        raw_transcript = generate_transcript(audio_filepath=audio_file, prompt_hint=prompt_hint)
    else:
        raw_transcript = test_transcript

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


def generate_todo_list(summaries):
    print(f"Running generate_todo_list on {len(summaries)} summaries")
    # Priority 5 is the highest, 1 is lowest
    todo_list = []
    for person in summaries:
        intents = ["to learn more about their company"]
        follow_ups = person.get("follow_ups", None)
        if follow_ups is None:
            intents.append("to thank you, say good to meet you")
        else:
            for follow_up in follow_ups:
                intents.append(f"to {follow_up}")

        outreaches = generate_first_outreaches(
            person["name"],
            person_transcript=person.get("transcript"),
            intents=intents
        )
        todo_list.extend(outreaches)

    print("=== All todo_list === ")
    print(json.dumps(todo_list))
    return todo_list
