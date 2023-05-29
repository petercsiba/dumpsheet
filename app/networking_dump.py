import json
import openai
import os
import pprint
import toml

from openai_utils import gpt_response_to_json, run_prompt, Timer
from storage_utils import mkdir_safe, write_to_csv

# config = toml.load('secrets.toml')
# openai.api_key = config["OPEN_API_KEY"]
# AUDIO_FILE = "input/networking-transcript-1-katka-tech-roast-may-25.mp4"
# command = f"ffmpeg -i input/{AUDIO_FILE} -c:v copy -c:a aac -strict experimental"
# result = subprocess.run(command, shell=True, capture_output=True, text=True)
# TODO: Time for local and production settings
# output_bucket = None
output_bucket = "katka-email-response"

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

# Check-points with test training data (so don't have to wait for the entire thing to re-run).
test_transcript = None
# test_transcript = """all right so listen up I met so many cool people today and this is just a quick quick rundown okay the terrible guy Vivek he is like a greasy I didn't like him he kept talking about his dick and how he's not intimidated by powerful women fuck him okay a super cool guy I met as the German guy there were two German guys um from Dresden one was Richard but he was making fun of it and maybe he should say that his name is dick as like the old American guys and he is I don't know CEO or whatever he has the u.com company they do the search and they have a couple of millions of users he says that because they're so they're small and they are quick to market they can compete and they want to disrupt the most profitable crowd jewel of google search so the u.com he also has AIX ventures and he invests into startups he was interested in the third pitch he says he might invest into it and he was like a cool down-to-earth German guy with wife and a kid so we could connect over there and he's from Dresden and his dad is his teacher at AHA TV the school where I went so it's funny okay the other German guy was Ben he is also I think he has a VC he was on the VC side and I don't know what he does he said he's going to add me on LinkedIn because our batteries were both dead and he's a single dad and he has a 10 year old 10 year old son and he's looking for a single mom okay next oh I met Ashley Ashley um she says she's accountant but I think it's fake her parents are Romanian she's from Canada and we look kind of alike she was so sweet and I just had so much fun talking to her okay next Dan Ross I think he is MD PhD works at Parnassus he's internist but he had the first pitch which were dragons and dungeons something I don't even remember what was it but we had such a good vibe and he and Ashley are homies and they really like each other and they hang out together so it was cool okay then I met Gulia who is in a biotech startup not biz dev but also in customer success and everything in between she is um she's Tatar and in Gulia and we connected on LinkedIn and she she's one of my new followers on TikTok yay okay next Jeff or Jeffrey he's like a cool Asian dude who went to Berkeley and his final senior year he went to I think Copenhagen or Germany he speaks fluent German oh my god and he worked in Copenhagen in a fintech startup and then when the pandemic hit he went nomading and now he's kind of coming back and he's looking for a job he's doing some hackathons with a couple of his friends he's not technical but he can do wireframes and whatnot and yeah then there's Roxy the only other woman on the panel she has a VC or something and she's a member in modernist and she said she would like to hang out again so I should reach out to her I said I'm going to reach out to her to her handle or whatever she had there okay next uh side note RoboSkills I don't know his full name this guy was so cool he was sitting behind me the Asian dude and he has 200 000 followers on both TikTok and Instagram and he says TikTok pays him two to three thousand dollars for his whatever so I think it's quite impressive okay next there is the like peacocking dressed cashier guy he has some crypto thing crypto thing crypto he's recording artist and he does interviews with like web3 people whatever he we connected on Instagram okay next oh yeah the bregs guy the bregs guy who was interested in matchmaking because he just doesn't he meets all these people he has all these new LinkedIn connections and he has no fucking clue how to just manage them so he was also talking about it but I didn't really connect with him one-on-one but yeah cool post more talking to him okay next um the girl Mary from Kyrgyzstan we had a quick conversation about me being in Kyrgyzstan and having a picture with their only female president Rosa so she liked that she says she's also a new content creator she has 120 followers and she's talking about mental health um her boy and she was pitching she was one of those um random audience pitches next uh her boyfriend I don't remember his name but he's doing data analytics content as well as of two months ago he quit his job he had a really cool hoodie I don't remember the name but he told me the name where he got it from it looked really cool okay let's think uh so there were four startups pitching okay then so the first one was Dan I already told you about him oh yeah there is the other okay there is the third startup pitching product smith there's a black dude which didn't put his on his probably he says he's co-founder he didn't put on his face on deck and the German guy Richard said that he's interested in the venture or whatever oh yeah and Gigi I don't think I have Gigi anywhere Gigi is Peter Evans's girlfriend and she is a toddler teacher at Mission Montessori and she couldn't go to the after party because she has the evaluation or whatever the parent teacher conference and she needs to finish the write-ups it would be cool to like I mean just connect with her and you know for the future so that at any we don't like Masha we have a backup oh yeah and then there's the Yemeni Canadian guy Ahmed he says he's a lawyer he's from a super privileged background like born here in San Jose but then his family moved back to Yemen and then where this where he grew up and they moved to Canada and then I think he studied he said he studied law in the UK because they have shorter degrees they have just three four years or whatnot and he's able to practice and is is his first time now here in California like tracing tracking his roots and we talked I mean he was super like he was kind of hitting on me but he was like super supportive of like me being culturally competent and I kind of liked it and I appreciate it I felt cool about it oh yeah okay and the next guy there is the VC guy LGBTQ VC who was throwing an LP event last week he told me about the the Caster the Academy which is social club in Castro I don't know if it's like LGBTQ only or not and we didn't have the best vibe but it was okay I would like to remember his name"""
test_get_names = None
# test_get_names = """['Vivek: Terrible guy who talks about his dick', 'Richard/Dick: CEO of u.com and AIX ventures, cool German guy', 'Ben: VC who is a single dad', 'Ashley: Possibly fake accountant, Romanian-Canadian', 'Dan Ross: MD PhD internist who pitched about dragons and dungeons', 'Gulia: Biotech startup person in customer success', 'Jeff/Jeffrey: Asian dude who spoke fluent German, looking for a job', 'Roxy: Woman with a VC who wants to hang out again', 'RoboSkills: Asian TikTok and Instagram influencer', 'Crypto Cashier guy: Recording artist and interviewer for web3', 'Bregs guy: Interested in matchmaking, has many LinkedIn connections', 'Mary: Content creator from Kyrgyzstan interested in mental health', "Mary's boyfriend: Data analytics content creator", 'Unidentified co-founder: Black dude pitching for Product Smith', "Gigi: Peter Evans's girlfriend who is a toddler teacher", 'Ahmed: Yemeni Canadian lawyer tracing his roots', 'The VC guy: LGBTQ VC throwing LP event, mentioned Caster Academy']"""
test_person_to_transcript = None
# test_person_to_transcript = """{"Vivek": ["he kept talking about his dick", "not intimidated by powerful women"], "Richard/Dick": ["there were two German guys um from Dresden one was Richard but he was making fun of it and maybe he should say that his name is dick as like the old American guys and he is I don't know CEO or whatever he has the u.com company", "he also has AIX ventures and he invests into startups"], "Ben": ["The other German guy was Ben he is also I think he has a VC he was on the VC side and I don't know what he does", "he's a single dad and he has a 10-year-old 10-year-old son and he's looking for a single mom"], "Ashley": ["Ashley um she says she's accountant but I think it's fake her parents are Romanian she's from Canada", "he and Ashley are homies and they really like each other and they hang out together so it was cool"], "Dan Ross": ["Dan Ross I think he is MD PhD works at Parnassus he's internist but he had the first pitch which were dragons and dungeons something I don't even remember what was it", "he and Ashley are homies and they really like each other and they hang out together so it was cool"], "Gulia": ["then I met Gulia who is in a biotech startup not biz dev but also in customer success and everything in between"], "Jeff/Jeffrey": ["next Jeff or Jeffrey he's like a cool Asian dude who went to Berkeley and his final senior year he went to I think Copenhagen or Germany he speaks fluent German oh my god and he worked in Copenhagen in a fintech startup and then when the pandemic hit he went nomading and now he's kind of coming back and he's looking for a job he's doing some hackathons with a couple of his friends he's not technical but he can do wireframes and whatnot"], "Roxy": ["then there's Roxy the only other woman on the panel she has a VC or something and she's a member in modernist and she said she would like to hang out again so I should reach out to her I said I'm going to reach out to her to her handle or whatever she had there"], "RoboSkills": ["side note RoboSkills I don't know his full name this guy was so cool he was sitting behind me the Asian dude and he has 200 000 followers on both TikTok and Instagram and he says TikTok pays him two to three thousand dollars for his whatever so I think it's quite impressive"], "Crypto Cashier guy": ["there is the like peacocking dressed cashier guy he has some crypto thing crypto thing crypto he's recording artist and he does interviews with like web3 people whatever he we connected on Instagram"], "Bregs guy": ["the bregs guy the bregs guy who was interested in matchmaking because he just doesn't he meets all these people he has all these new LinkedIn connections and he has no fucking clue how to just manage them so he was also talking about it", "cool post more talking to him"], "Mary": ["um the girl Mary from Kyrgyzstan we had a quick conversation about me being in Kyrgyzstan and having a picture with their only female president Rosa so she liked that she says she's also a new content creator she has 120 followers and she's talking about mental health"], "Mary's boyfriend": ["her boyfriend I don't remember his name but he's doing data analytics content as well as of two months ago he quit his job he had a really cool hoodie I don't remember the name but he told me the name where he got it from it looked really cool"], "Unidentified co-founder": ["there is the third startup pitching product smith there's a black dude which didn't put his on his probably he says he's co-founder he didn't put on his face on deck"], "Gigi": ["oh yeah and Gigi I don't think I have Gigi anywhere Gigi is Peter Evans's girlfriend and she is a toddler teacher at Mission Montessori and she couldn't go to the after party because she has the evaluation or whatever the parent teacher conference and she needs to finish the write-ups it would be cool to like I mean just connect with her and you know for the future so that at any we don't like Masha we have a backup"], "Ahmed": ["oh yeah and then there's the Yemeni Canadian guy Ahmed he says he's a lawyer he's from a super privileged background like born here in San Jose but then his family moved back to Yemen and then where this where he grew up and they moved to Canada and then I think he studied he said he studied law in the UK because they have shorter degrees they have just three four years or whatnot and he's able to practice and is is his first time now here in California like tracing tracking his roots and we talked I mean he was super like he was kind of hitting on me but he was like super supportive of like me being culturally competent and I kind of liked it and I appreciate it I felt cool about it"], "The VC guy": ["oh yeah and the next guy there is the VC guy LGBTQ VC who was throwing an LP event last week he told me about the the Caster the Academy which is social club in Castro I don't know if it's like LGBTQ only or not and we didn't have the best vibe but it was okay I would like to remember his name"]}"""
test_summaries = None
# test_summaries = """[{"name": "Vivek", "from": null, "industry": null, "vibes": "Not impressed, he kept talking about his dick. Also seemed to have a problem with powerful women.", "priority": 1, "needs": null, "contact_info": null, "follow_ups": null, "transcript": ["he kept talking about his dick", "not intimidated by powerful women"]}, {"name": "Richard/Dick", "from": "Dresden", "industry": null, "vibes": "He was making fun of his own name, which gave me a good impression of his sense of humor. He seemed confident and knowledgeable about his companies.", "priority": 4, "needs": null, "contact_info": "Not mentioned", "follow_ups": ["- Look up more information about u.com and AIX ventures", "- Connect with Richard on LinkedIn"], "transcript": ["there were two German guys um from Dresden one was Richard but he was making fun of it and maybe he should say that his name is dick as like the old American guys and he is I don't know CEO or whatever he has the u.com company", "he also has AIX ventures and he invests into startups"]}, {"name": "Ben", "from": "Germany", "industry": null, "vibes": "Seems friendly, but not sure what he does", "priority": 3, "needs": ["Looking for a single mom"], "contact_info": null, "follow_ups": ["Ask Ben what his specialty is in VC"], "transcript": ["The other German guy was Ben he is also I think he has a VC he was on the VC side and I don't know what he does", "he's a single dad and he has a 10-year-old 10-year-old son and he's looking for a single mom"]}, {"name": "Dan Ross", "from": null, "industry": "medicine", "vibes": "Seems like an interesting person with diverse interests. Apparently close with Ashley.", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Ask about his experience in both medicine and gaming."], "transcript": ["Dan Ross I think he is MD PhD works at Parnassus he's internist but he had the first pitch which were dragons and dungeons something I don't even remember what was it", "he and Ashley are homies and they really like each other and they hang out together so it was cool"]}, {"name": "Gulia", "from": null, "industry": "biotech", "vibes": "positive, seems knowledgeable and versatile", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Learn more about Gulia's startup and her role"], "transcript": ["then I met Gulia who is in a biotech startup not biz dev but also in customer success and everything in between"]}, {"name": "Jeff/Jeffrey", "from": "Berkeley", "industry": "fintech", "vibes": "cool Asian dude, fluent in German", "priority": 4, "needs": ["job"], "contact_info": null, "follow_ups": ["send him some job listings"], "transcript": ["next Jeff or Jeffrey he's like a cool Asian dude who went to Berkeley and his final senior year he went to I think Copenhagen or Germany he speaks fluent German oh my god and he worked in Copenhagen in a fintech startup and then when the pandemic hit he went nomading and now he's kind of coming back and he's looking for a job he's doing some hackathons with a couple of his friends he's not technical but he can do wireframes and whatnot"]}, {"name": "Roxy", "from": null, "industry": "VC or something, member in modernist", "vibes": "positive, she said she would like to hang out again", "priority": 4, "needs": null, "contact_info": "handle or whatever she had there", "follow_ups": ["reach out to her"], "transcript": ["then there's Roxy the only other woman on the panel she has a VC or something and she's a member in modernist and she said she would like to hang out again so I should reach out to her I said I'm going to reach out to her to her handle or whatever she had there"]}, {"name": "RoboSkills", "from": null, "industry": null, "vibes": "this guy was so cool", "priority": 4, "needs": null, "contact_info": "Instagram, TikTok", "follow_ups": ["Ask him about his content creation process", "Get tips on growing social media following"], "transcript": ["side note RoboSkills I don't know his full name this guy was so cool he was sitting behind me the Asian dude and he has 200 000 followers on both TikTok and Instagram and he says TikTok pays him two to three thousand dollars for his whatever so I think it's quite impressive"]}, {"name": "Crypto Cashier guy", "from": null, "industry": "crypto", "vibes": "he seemed interesting and passionate about crypto", "priority": 3, "needs": null, "contact_info": "Instagram", "follow_ups": ["check out his recordings and interviews with web3 people"], "transcript": ["there is the like peacocking dressed cashier guy he has some crypto thing crypto thing crypto he's recording artist and he does interviews with like web3 people whatever he we connected on Instagram"]}, {"name": "Bregs guy", "from": null, "industry": null, "vibes": "Seems interested in matchmaking, but also a bit lost", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["Discuss his matchmaking interests further", "See if there's any way I can help him manage his LinkedIn connections better"], "transcript": ["the bregs guy the bregs guy who was interested in matchmaking because he just doesn't he meets all these people he has all these new LinkedIn connections and he has no fucking clue how to just manage them so he was also talking about it", "cool post more talking to him"]}, {"name": "Mary", "from": "Kyrgyzstan", "industry": null, "vibes": "Positive, friendly and interested", "priority": 3, "needs": ["Looking for growth opportunities as a content creator", "Interested in mental health topics"], "contact_info": null, "follow_ups": ["Share contacts and resources for content creation", "Offer collaboration on mental health related content"], "transcript": ["um the girl Mary from Kyrgyzstan we had a quick conversation about me being in Kyrgyzstan and having a picture with their only female president Rosa so she liked that she says she's also a new content creator she has 120 followers and she's talking about mental health"]}, {"name": "Mary's boyfriend", "from": null, "industry": "data analytics content", "vibes": "cool hoodie", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["ask for the name of the hoodie and where to get it"], "transcript": ["her boyfriend I don't remember his name but he's doing data analytics content as well as of two months ago he quit his job he had a really cool hoodie I don't remember the name but he told me the name where he got it from it looked really cool"]}, {"name": "Unidentified co-founder", "from": null, "industry": null, "vibes": "I didn't get much information about him except for the fact that he is a black dude and a co-founder of Product Smith, so I can't really say much about my first impression or vibes.", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["Find out more about Product Smith and their co-founder."], "transcript": ["there is the third startup pitching product smith there's a black dude which didn't put his on his probably he says he's co-founder he didn't put on his face on deck"]}, {"name": "Gigi", "from": null, "industry": null, "vibes": "I don't know her but seems nice, dedicated to her job as a toddler teacher", "priority": 3, "needs": ["to finish write-ups for parent-teacher conference"], "contact_info": null, "follow_ups": ["Connect with her for future networking opportunities"], "transcript": ["oh yeah and Gigi I don't think I have Gigi anywhere Gigi is Peter Evans's girlfriend and she is a toddler teacher at Mission Montessori and she couldn't go to the after party because she has the evaluation or whatever the parent teacher conference and she needs to finish the write-ups it would be cool to like I mean just connect with her and you know for the future so that at any we don't like Masha we have a backup"]}, {"name": "Ahmed", "from": ["San Jose", "Yemen", "Canada", null], "industry": null, "vibes": "he was super supportive of me being culturally competent and I kind of liked it and felt cool about it.", "priority": 3, "needs": null, "contact_info": ["text", "LinkedIn", "Instagram", null], "follow_ups": ["Follow up on his legal background and experience.", "Clarify his cultural competency initiatives."], "transcript": ["oh yeah and then there's the Yemeni Canadian guy Ahmed he says he's a lawyer he's from a super privileged background like born here in San Jose but then his family moved back to Yemen and then where this where he grew up and they moved to Canada and then I think he studied he said he studied law in the UK because they have shorter degrees they have just three four years or whatnot and he's able to practice and is is his first time now here in California like tracing tracking his roots and we talked I mean he was super like he was kind of hitting on me but he was like super supportive of like me being culturally competent and I kind of liked it and I appreciate it I felt cool about it"]}, {"name": "The VC guy", "from": null, "industry": "Venture Capital", "vibes": "okay", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["Find out more about the Caster Academy social club in Castro."], "transcript": ["oh yeah and the next guy there is the VC guy LGBTQ VC who was throwing an LP event last week he told me about the the Caster the Academy which is social club in Castro I don't know if it's like LGBTQ only or not and we didn't have the best vibe but it was okay I would like to remember his name"]}]"""
#test_summaries = """[{"name": "Valentina", "from": null, "industry": "Venture Capital", "vibes": "Positive", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Follow up with Valentina from Vibranium VC"], "transcript": ["The first person I talked with, Valentina from Vibranium VC", "she invited me"], "full_name": null, "profile_url": null}, {"name": "Alexander", "from": null, "industry": "Cleantech", "vibes": "We didn't really talk that much, so I don't have strong vibes about him.", "priority": 3, "needs": null, "contact_info": null, "follow_ups": null, "transcript": ["there was a guy called Alexander that I had a conversation with", "he is in Cleantech", "we didn't really talk that much"], "full_name": null, "profile_url": null}, {"name": "Wojciech Kretowski", "from": "Poland", "industry": null, "vibes": "My first impression of Wojciech was positive. He was friendly and engaged in our conversation.", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Follow up after Alchemist accelerator to see how their startup is progressing.", "Consider sharing any relevant resources or connections that may be helpful for them."], "transcript": ["he introduced me to two Polish founders that do a startup called Dekognity", "The name of the founders is Wojciech Kretowski", "pretty early stage", "they're going to be doing the Alchemist accelerator, this cohort."], "full_name": null, "profile_url": null}, {"name": "Katarzyna Stankiewicz", "from": "Poland", "industry": null, "vibes": "I had a great first impression of Katarzyna. She was articulate and enthusiastic about her startup idea.", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Follow up after the Alchemist accelerator to see how the startup is progressing."], "transcript": ["he introduced me to two Polish founders that do a startup called Dekognity", "The name of the founders is Katarzyna Stankiewicz", "just graduating from Imperial in data science", "teaching people, it's like duolingo for teaching like social skills", "very early stage", "they're going to be doing the Alchemist accelerator, this cohort."], "full_name": null, "profile_url": null}, {"name": "Abishek Chopra", "from": null, "industry": "quantum computing", "vibes": "I thought he was pretty knowledgeable about the topic", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["Look for any potential collaboration opportunities"], "transcript": ["there was a guy called Abishek Chopra", "he is in quantum computing"], "full_name": null, "profile_url": null}, {"name": "Miguel Coelho", "from": "Dubai", "industry": "B2B SaaS", "vibes": "Seems interesting and accomplished with experience in Salesforce and SAP.", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["Add him to my network."], "transcript": ["Then I also talked to Miguel Coelho who did a work on MBA and he's he worked at Salesforce and SAP before. And he has a B2B SaaS startup, which might be interesting for us, but he is probably he's based in Dubai and he has a startup here.", "So it's probably not relevant when it comes to geography. But I would just like to have him in my network, basically."], "full_name": null, "profile_url": null}, {"name": "Daria Derkach", "from": null, "industry": "Engineering/Technology", "vibes": "Positive", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Research more about her sector focus and areas she can provide a second opinion on", "Consider reaching out to her for mentorship or advice"], "transcript": ["Also for me, just as a next step, not really like sort of quantity to any person, I talked with the people from the Alchemist, but I don't like, I didn't catch their name or we didn't change, exchange names.", "So that would just be interesting to have it in mind that if I ever need to contact somebody from Alchemist just to know someone there, but I don't remember the name, but I'm sure that I can find it when I have time.", "Then I also had a chat with, give me a second, with a woman who just became a mentor. Her name is Daria Derkach and she's engineering manager at Atlassian.", "She's mentor at First Round and Berkeley Skydeck.", "What I would like to know more about her is basically what is sort of her sector focus and also what she could basically give a second opinion on when we ever need that."], "full_name": null, "profile_url": null}]"""


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
        Output format: json map of name to list of substrings
        Try to use up all words from the transcript and include extra context for those substrings
        People: {}
        Transcript: {}
        """.format(sublist, raw_transcript)
        raw_response = run_prompt(query_mentions)
        people = gpt_response_to_json(raw_response)
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
    * from: where are they from, or null if i don't mention it 
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
            print(f"Getting all mentions for {name}")
            # TODO: We might need to go back to the original slicing? Or at least somehow attribute the missing parts
            raw_response = run_prompt(query_summarize.format(transcript), print_prompt=True)

            summary = gpt_response_to_json(raw_response)
            if summary is None:
                continue
            summary["name"] = name
            summary["transcript"] = transcript
            summaries.append(summary)

    # A super-basic "TODO" list is just a few extra columns so lets do that
    for i, _ in enumerate(summaries):
        summary["todo_full_name"] = None
        summary["todo_profile_url"] = None

    return summaries


# Input is a dictionary of fields to values
# Output is list of candidate texts
def generate_first_outreaches(person, intents):
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
        Only output the resulting message. 
        My knowledge of the person is encoded as a JSON struct: {}
        """.format(intent, person)
        raw_response = run_prompt(query_outreaches)
        result.append({
            "name": person["name"],
            "message_type": intent,
            "outreach": raw_response,
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
    summaries = sorted(summaries, key=lambda x: x['priority'], reverse=True)
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

        person_copy = dict(person)
        # To make it personalized, the transcript must be present. Otherwise generates generic corp BS.
        # del(person_copy["transcript"])
        del(person_copy["follow_ups"])

        outreaches = generate_first_outreaches(person_copy, intents=intents)
        todo_list.extend(outreaches)

    print(json.dumps(todo_list))
    return todo_list


# if __name__ == "__main__":
# TODO: Fill in from app.py
    # write_to_csv(todo_list, f"{output_prefix}-todo.csv")
#    networking_dump(AUDIO_FILE, OUTPUT_FILE_PREFIX)