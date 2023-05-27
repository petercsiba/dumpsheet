import json
import openai
import os
import pprint
import toml

from openai_utils import gpt_response_to_json, run_prompt, Timer
from storage_utils import mkdir_safe, write_to_csv

config = toml.load('secrets.toml')
openai.api_key = config["OPEN_API_KEY"]
# TODO(peter): Why OpenAI says that it is NOT mp4?
#    ffmpeg -i input/original.mp4 -c:v copy -c:a aac -strict experimental input/converted.mp4
# AUDIO_FILE = "input/networking-transcript-1-katka-tech-roast-may-25.mp4"
AUDIO_FILE = "input/converted.mp4"
mkdir_safe("output")
OUTPUT_FILE_PREFIX = "output/summaries"  # will do .json, .csv sepately

pp = pprint.PrettyPrinter(indent=4)


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
    with open(AUDIO_FILE, "rb") as audio_file:
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
            return transcript["text"]

# Check-points with test training data (so don't have to wait for the entire thing to re-run).
# test_transcript = None
test_transcript = """all right so listen up I met so many cool people today and this is just a quick quick rundown okay the terrible guy Vivek he is like a greasy I didn't like him he kept talking about his dick and how he's not intimidated by powerful women fuck him okay a super cool guy I met as the German guy there were two German guys um from Dresden one was Richard but he was making fun of it and maybe he should say that his name is dick as like the old American guys and he is I don't know CEO or whatever he has the u.com company they do the search and they have a couple of millions of users he says that because they're so they're small and they are quick to market they can compete and they want to disrupt the most profitable crowd jewel of google search so the u.com he also has AIX ventures and he invests into startups he was interested in the third pitch he says he might invest into it and he was like a cool down-to-earth German guy with wife and a kid so we could connect over there and he's from Dresden and his dad is his teacher at AHA TV the school where I went so it's funny okay the other German guy was Ben he is also I think he has a VC he was on the VC side and I don't know what he does he said he's going to add me on LinkedIn because our batteries were both dead and he's a single dad and he has a 10 year old 10 year old son and he's looking for a single mom okay next oh I met Ashley Ashley um she says she's accountant but I think it's fake her parents are Romanian she's from Canada and we look kind of alike she was so sweet and I just had so much fun talking to her okay next Dan Ross I think he is MD PhD works at Parnassus he's internist but he had the first pitch which were dragons and dungeons something I don't even remember what was it but we had such a good vibe and he and Ashley are homies and they really like each other and they hang out together so it was cool okay then I met Gulia who is in a biotech startup not biz dev but also in customer success and everything in between she is um she's Tatar and in Gulia and we connected on LinkedIn and she she's one of my new followers on TikTok yay okay next Jeff or Jeffrey he's like a cool Asian dude who went to Berkeley and his final senior year he went to I think Copenhagen or Germany he speaks fluent German oh my god and he worked in Copenhagen in a fintech startup and then when the pandemic hit he went nomading and now he's kind of coming back and he's looking for a job he's doing some hackathons with a couple of his friends he's not technical but he can do wireframes and whatnot and yeah then there's Roxy the only other woman on the panel she has a VC or something and she's a member in modernist and she said she would like to hang out again so I should reach out to her I said I'm going to reach out to her to her handle or whatever she had there okay next uh side note RoboSkills I don't know his full name this guy was so cool he was sitting behind me the Asian dude and he has 200 000 followers on both TikTok and Instagram and he says TikTok pays him two to three thousand dollars for his whatever so I think it's quite impressive okay next there is the like peacocking dressed cashier guy he has some crypto thing crypto thing crypto he's recording artist and he does interviews with like web3 people whatever he we connected on Instagram okay next oh yeah the bregs guy the bregs guy who was interested in matchmaking because he just doesn't he meets all these people he has all these new LinkedIn connections and he has no fucking clue how to just manage them so he was also talking about it but I didn't really connect with him one-on-one but yeah cool post more talking to him okay next um the girl Mary from Kyrgyzstan we had a quick conversation about me being in Kyrgyzstan and having a picture with their only female president Rosa so she liked that she says she's also a new content creator she has 120 followers and she's talking about mental health um her boy and she was pitching she was one of those um random audience pitches next uh her boyfriend I don't remember his name but he's doing data analytics content as well as of two months ago he quit his job he had a really cool hoodie I don't remember the name but he told me the name where he got it from it looked really cool okay let's think uh so there were four startups pitching okay then so the first one was Dan I already told you about him oh yeah there is the other okay there is the third startup pitching product smith there's a black dude which didn't put his on his probably he says he's co-founder he didn't put on his face on deck and the German guy Richard said that he's interested in the venture or whatever oh yeah and Gigi I don't think I have Gigi anywhere Gigi is Peter Evans's girlfriend and she is a toddler teacher at Mission Montessori and she couldn't go to the after party because she has the evaluation or whatever the parent teacher conference and she needs to finish the write-ups it would be cool to like I mean just connect with her and you know for the future so that at any we don't like Masha we have a backup oh yeah and then there's the Yemeni Canadian guy Ahmed he says he's a lawyer he's from a super privileged background like born here in San Jose but then his family moved back to Yemen and then where this where he grew up and they moved to Canada and then I think he studied he said he studied law in the UK because they have shorter degrees they have just three four years or whatnot and he's able to practice and is is his first time now here in California like tracing tracking his roots and we talked I mean he was super like he was kind of hitting on me but he was like super supportive of like me being culturally competent and I kind of liked it and I appreciate it I felt cool about it oh yeah okay and the next guy there is the VC guy LGBTQ VC who was throwing an LP event last week he told me about the the Caster the Academy which is social club in Castro I don't know if it's like LGBTQ only or not and we didn't have the best vibe but it was okay I would like to remember his name"""
# test_slicing = None
test_slicing = """[{'name': 'Vivek', 'start_index': 11, 'end_index': 27}, {'name': 'Richard', 'start_index': 56, 'end_index': 104}, {'name': 'Ben', 'start_index': 107, 'end_index': 146}, {'name': 'Ashley', 'start_index': 149, 'end_index': 163}, {'name': 'Dan Ross', 'start_index': 165, 'end_index': 215}, {'name': 'Gulia', 'start_index': 217, 'end_index': 261}, {'name': 'Jeff/ Jeffrey', 'start_index': 262, 'end_index': 316}, {'name': 'Roxy', 'start_index': 318, 'end_index': 350}, {'name': 'RoboSkills', 'start_index': 352, 'end_index': 372}, {'name': 'Cashier guy', 'start_index': 373, 'end_index': 387}, {'name': 'Bregs guy', 'start_index': 394, 'end_index': 426}, {'name': 'Mary', 'start_index': 427, 'end_index': 442}, {'name': "Mary's boyfriend", 'start_index': 444, 'end_index': 468}, {'name': 'Product Smith co-founder', 'start_index': 483, 'end_index': 504}, {'name': 'Ahmed', 'start_index': 537, 'end_index': 572}, {'name': 'LGBTQ VC guy', 'start_index': 580, 'end_index': 607}]"""
# test_slicing = """[{'name': 'Vivek', 'start_index': 13, 'end_index': 21}, {'name': 'Richard', 'start_index': 34, 'end_index': 70}, {'name': 'Ben', 'start_index': 73, 'end_index': 99}, {'name': 'Ashley', 'start_index': 102, 'end_index': 114}, {'name': 'Dan Ross', 'start_index': 115, 'end_index': 154}, {'name': 'Gulia', 'start_index': 155, 'end_index': 196}, {'name': 'Jeff or Jeffrey', 'start_index': 197, 'end_index': 238}, {'name': 'Roxy', 'start_index': 239, 'end_index': 250}, {'name': 'RoboSkills', 'start_index': 251, 'end_index': 262}, {'name': 'Cashier guy', 'start_index': 263, 'end_index': 273}, {'name': 'Bregs guy', 'start_index': 278, 'end_index': 291}, {'name': 'Mary', 'start_index': 292, 'end_index': 305}, {'name': "Mary's boyfriend", 'start_index': 306, 'end_index': 321}, {'name': 'Product smith co-founder', 'start_index': 332, 'end_index': 350}, {'name': 'Ahmed', 'start_index': 409, 'end_index': 437}, {'name': 'LGBTQ VC guy', 'start_index': 473, 'end_index': 489}]"""
test_summaries = None
test_summaries = """{'Vivek': {'name': 'Vivek', 'from': null, 'industry': null, 'vibes': 'terrible guy, greasy, talks about his dick', 'priority': 1, 'needs': null, 'contact_info': null, 'follow_ups': null}, 'Richard': {'name': 'Richard', 'from': 'Dresden', 'industry': null, 'vibes': 'super cool guy', 'priority': 4, 'needs': null, 'contact_info': null, 'follow_ups': null}, 'Ben': {'name': 'Ben', 'from': null, 'industry': 'search', 'vibes': 'cool guy', 'priority': 3, 'needs': null, 'contact_info': null, 'follow_ups': null}, 'Ashley': {'name': 'Ashley', 'from': 'Canada', 'industry': null, 'vibes': 'fake accountant, looks alike', 'priority': 2, 'needs': null, 'contact_info': null, 'follow_ups': null}, 'Dan Ross': {'name': 'Dan Ross', 'from': 'Dresden', 'industry': 'startup investor', 'vibes': 'cool, down-to-earth guy', 'priority': 4, 'needs': null, 'contact_info': null, 'follow_ups': 'interested in third pitch, might invest'}, 'Gulia': {'name': 'Gulia', 'from': null, 'industry': 'biotech', 'vibes': null, 'priority': 2, 'needs': null, 'contact_info': 'LinkedIn', 'follow_ups': null}, 'Jeff/ Jeffrey': {'name': 'Jeff/ Jeffrey', 'from': null, 'industry': 'fintech', 'vibes': 'cool Asian dude', 'priority': 3, 'needs': 'looking for a job, doing hackathons', 'contact_info': null, 'follow_ups': null}, 'Roxy': {'name': 'Roxy', 'from': null, 'industry': 'VC', 'vibes': 'sweet, fun to talk to', 'priority': 3, 'needs': null, 'contact_info': null, 'follow_ups': 'wants to hang out again'}, 'RoboSkills': {'name': 'RoboSkills', 'from': null, 'industry': null, 'vibes': 'cool guy, 200k followers on TikTok and Instagram', 'priority': 3, 'needs': null, 'contact_info': null, 'follow_ups': null}, 'Cashier guy': {'name': 'Cashier guy', 'from': null, 'industry': 'crypto', 'vibes': 'peacocking dressed, recording artist, does interviews', 'priority': 2, 'needs': null, 'contact_info': 'Instagram', 'follow_ups': null}, 'Bregs guy': {'name': 'Bregs guy', 'from': null, 'industry': null, 'vibes': null, 'priority': 2, 'needs': 'interested in matchmaking and managing LinkedIn connections', 'contact_info': null, 'follow_ups': 'cool to post more talking to him'}, 'Mary': {'name': 'Mary', 'from': 'Kyrgyzstan', 'industry': null, 'vibes': null, 'priority': 2, 'needs': 'new content creator, talking about mental health', 'contact_info': null, 'follow_ups': null}, "Mary's boyfriend": {'name': "Mary's boyfriend", 'from': null, 'industry': 'data analytics', 'vibes': 'cool, has a really cool hoodie', 'priority': 2, 'needs': null, 'contact_info': null, 'follow_ups': null}, 'Ahmed': {'name': 'Ahmed', 'from': 'San Jose', 'industry': 'law', 'vibes': 'super supportive, kind of hitting on me', 'priority': 2, 'needs': null, 'contact_info': null, 'follow_ups': null}, 'LGBTQ VC guy': {'name': 'LGBTQ VC guy', 'from': null, 'industry': 'VC', 'vibes': null, 'priority': 2, 'needs': null, 'contact_info': null, 'follow_ups': 'mentioned the Caster Academy'}, 'Gigi': {'name': 'Gigi', 'from': null, 'industry': null, 'vibes': null, 'priority': 1, 'needs': null, 'contact_info': null, 'follow_ups': 'partner of Peter Evans, toddler teacher at Mission Montessori'}}"""
# test_summaries = """[  {    "name": "Vivek",    "from": null,    "industry": null,    "vibes": "greasy, talked about his penis, not a fan",    "priority": 1,    "needs": null,    "contact_info": null,    "follow_ups": null  },  {    "name": "Richard/Dick",    "from": "Dresden",    "industry": "CEO of u.com, also invests in startups",    "vibes": "cool, down-to-earth, interested in third pitch",    "priority": 4,    "needs": null,    "contact_info": null,    "follow_ups": "connect over being from the same school"  },  {    "name": "Ben",    "from": null,    "industry": "VC",    "vibes": null,    "priority": 3,    "needs": "looking for single mom (for dating?)",    "contact_info": "adding on LinkedIn",    "follow_ups": null  },  {    "name": "Ashley",    "from": "Canada",    "industry": "Possibly accountant",    "vibes": "sweet, enjoyable to talk to",    "priority": 2,    "needs": null,    "contact_info": null,    "follow_ups": null  },  {    "name": "Dan Ross",    "from": null,    "industry": "MD PhD, internist at Parnassus",    "vibes": "good, had a good vibe with Ashley",    "priority": 4,    "needs": null,    "contact_info": null,    "follow_ups": "connect over shared interests"  },  {    "name": "Gulia",    "from": null,    "industry": "Biotech startup",    "vibes": null,    "priority": 2,    "needs": null,    "contact_info": "connected on LinkedIn",    "follow_ups": null  },  {    "name": "Jeff/Jeffrey",    "from": "Berkeley",    "industry": "Fintech",    "vibes": "cool, speaks fluent German",    "priority": 3,    "needs": null,    "contact_info": null,    "follow_ups": null  },  {    "name": "Roxy",    "from": null,    "industry": "VC",    "vibes": null,    "priority": 3,    "needs": null,    "contact_info": "reach out on Instagram",    "follow_ups": null  },  {    "name": "RoboSkills",    "from": null,    "industry": "TikTok star/Influencer",    "vibes": "impressive",    "priority": 2,    "needs": null,    "contact_info": null,    "follow_ups": null  },  {    "name": "Crypto artist/Interviewer",    "from": null,    "industry": "Crypto",    "vibes": null,    "priority": 1,    "needs": null,    "contact_info": "connected on Instagram",    "follow_ups": null  },  {    "name": "Bregs guy",    "from": null,    "industry": "Unknown/interested in matchmaking",    "vibes": null,    "priority": 2,    "needs": null,    "contact_info": "plan to talk more",    "follow_ups": null  },  {    "name": "Mary",    "from": "Kyrgyzstan",    "industry": null,    "vibes": null,    "priority": 1,    "needs": null,    "contact_info": null,    "follow_ups": null  },  {    "name": "Mary's boyfriend",    "from": null,    "industry": "Data analytics",    "vibes": "cool hoodie",    "priority": 2,    "needs": null,    "contact_info": null,    "follow_ups": null  },  {    "name": "Dan",    "from": null,    "industry": "Dragons and Dungeons?",    "vibes": "good",    "priority": 3,    "needs": null,    "contact_info": null,    "follow_ups": "connect over shared interests"  },  {    "name": "Gigi",    "from": null,    "industry": "Toddler teacher at Mission Montessori",    "vibes": null,    "priority": 2,    "needs": null,    "contact_info": null,    "follow_ups": "potential backup"  },  {    "name": "Ahmed",    "from": "Born in San Jose, lived in Yemen and Canada",    "industry": "Lawyer",    "vibes": "hitting on me, culturally competent",    "priority": 2,    "needs": null,    "contact_info": null,    "follow_ups": "potential connection for future"  },  {    "name": "LGBTQ VC guy",    "from": null,    "industry": "LGBTQ VC",    "vibes": null,    "priority": 2,    "needs": null,    "contact_info": null,    "follow_ups": null  },  {    "name": "Product smith co-founder",    "from": null,    "industry": null,    "vibes": null,    "priority": 2,    "needs": null,    "contact_info": null,    "follow_ups": "connect over Richard's possible investment"  }]"""


def slice_transcript(transcript):
    transcript_words = transcript.split()
    token_count = len(transcript_words)
    print(f"Transcript has {token_count} words")

    # Now the problem here is that we potentially have a longer transcript then the max (4096) tokens
    # Two approaches:
    # * Slice up the original string with overlaps
    #   Retrospective: would been faster to implement, BUT lest control over substrings used
    # * (this approach) Two phase
    #   * First slice it per person
    #   * Then send up to 2048 tokens per query
    query1 = """
    The following transcript talks about several different people, 
    I want you to slice the transcript into list of substrings, one substring for each of the person.
    For slicing I often use words like next, um or okay usually mean the next person is starting.
    Another hint is to watch for use of he or she, which usually means I continue talking about the same person. 
    Also if the scription changes from "he" to "she" or vice versa then it is a different person.
    Return the response as a valid json array and for each substring:
    * name: persons name or how I referenced them
    * start_index: index of the first word by number of words before it
    * end_index: index of the last word by number of words before it
    The transcript: {}
    """
    # Make sure to include the whole string without gaps.
    assert(token_count < 3500)  # todo implement this case
    if test_slicing is None:
        # Takes about 40 seconds
        raw_response = run_prompt(query1.format(transcript))
        intervals = gpt_response_to_json(raw_response)
    else:
        intervals = gpt_response_to_json(test_slicing)

    # The above prompt doesn't work perfect, two categories of mistakes:
    # * Big gaps -> never parsed those
    # * Sliced too eagerly
    # For the gaps we can use
    for i, interval in enumerate(intervals):
        intervals[i]["next_start"] = intervals[i+1]["start_index"] if i + 1 < len(intervals) else token_count
        intervals[i]["prev_end"] = intervals[i-1]["end_index"] if i - 1 >= 0 else 0
    person_to_transcript = {}
    for i, interval in enumerate(intervals):
        # If there is a gap it's hard to say which person it belongs to so for now including the gap for both.
        # TODO: Maybe it's better to do a middle between start and prev_end
        start = interval["prev_end"]
        # end = interval["end"]
        end = interval["next_start"]
        # Sometimes the slicing ain't ideal with GPT3.5 so just bluntly include two of these
        # end = slice_indexes[i+1]["next_start"] if i + 1 < len(slice_indexes) else interval["next_start"]
        # transcript[start:end]
        # TODO: Handle the case when it returns character index instead of the word index
        substring = " ".join(transcript_words[start:end])
        person_to_transcript[interval["name"]] = substring
    return person_to_transcript


# TODO: Assess what is a good amount of transcripts to send at the same time
def per_person_transcripts_to_summaries(person_to_transcript):
    # These we can derive later in the "keep your relationship warm" funnel.
    # * location: currently located at, or null if i don't mention it
    # * next_message_drafts: ideas of messages i can reach out with which have some value to them
    # * desires: what they want to achieve long-term, null for empty
    # * offers: list of skills they have, topics they understand or services they advertise, null for empty
    query2 = """
        I want you to summarize my notes from a networking event,
        input is a json dict mapping persons name or identifier to my note,
        the desired output is again a json dict which maps persons name to the following json key value object:
    * name: name
    * from: where are they from, or null if i don't mention it 
    * industry: one two works for the are of their specialty, or null if not sure
    * vibes: my first impression and general vibes of them
    * priority: on scale from 1 to 5 how excited i am to follow up, never null 
    * needs: list of what they are looking for soon or right now, null for empty
    * contact_info: what channel we can contact like text, sms, linkedin, instagram and similar or null if none
    * follow_ups: list of action items or follow ups i mentioned, null if none 
    the promised map of notes per person {}"""
    if test_summaries is None:
        # Can take minutes
        raw_response = run_prompt(query2.format(person_to_transcript))
        # TODO: Handle case when:
        #   I apologize, but it seems like the notes you provided are not in a uniform format, making it difficult to extract information accurately. Could you please provide me with notes that are structured in a standardized format such as bullet points or numbered lists?
        # result = gpt_response_to_json(raw_response)
        print(raw_response)
        summaries = gpt_response_to_json(raw_response)
    else:
        summaries = gpt_response_to_json(test_summaries)

    if len(person_to_transcript) != len(summaries):
        print(f"WARNING: Unexpected length of summaries {len(person_to_transcript)} != {len(summaries)}")
    for name, transcript in person_to_transcript.items():
        # Save the original transcript for each summary
        if name not in summaries:
            print(f"NOTE: could NOT find {name} in summaries, adding it, might have duplicates")
            summaries[name] = {"name": name, "transcript": transcript}
        else:
            summaries[name]["transcript"] = transcript
    return summaries


def main():
    if test_transcript is None:
        prompt_hint = "notes from a networking event about the new people I met with my impressions and follow up ideas"
        transcript = generate_transcript(audio_filepath=AUDIO_FILE, prompt_hint=prompt_hint)
    else:
        transcript = test_transcript
    person_to_transcript = slice_transcript(transcript=transcript)

    # Slice the longer list into smaller sublists
    # size = 8
    # sublists = [sliced_transcript[i:i + size] for i in range(0, len(sliced_transcript), size)]
    # # Process each sublist and store the results
    # summaries = []
    # for sublist in sublists:
    #     sublist_result = per_person_transcripts_to_summaries(sublist)
    #     summaries.extend(sublist_result)
    person_to_summary = per_person_transcripts_to_summaries(person_to_transcript)
    pp.pprint(person_to_summary)
    summaries = list(person_to_summary.values())
    with open(f"{OUTPUT_FILE_PREFIX}.json", 'w') as handle:
        json.dump(summaries, handle)
    write_to_csv(summaries, f"{OUTPUT_FILE_PREFIX}.csv")


if __name__ == "__main__":
    main()