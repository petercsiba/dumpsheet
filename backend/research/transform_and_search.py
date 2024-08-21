import csv
import json
import os
import random
import time

import openai
import toml

from gpt_form_filler.openai_client import OpenAiClient, gpt_response_to_json

from common.gpt_client import open_ai_client_with_db_cache

# from app.storage_utils import write_to_csv

config = toml.load("secrets.toml")
openai.api_key = config["OPEN_API_KEY"]

output_folder = "data"
MATCH_OUTPUT = f"{output_folder}/matched_data_{time.time()}.json"
SCRAPED_OUTPUT = f"{output_folder}/scraped_data.json"
TRANSFORMED_OUTPUT = f"{output_folder}/transformed_data.csv"


def slice_dictionary(original_dict):
    keys = list(original_dict.keys())[:2]
    sliced_dict = {key: original_dict[key] for key in keys}
    return sliced_dict


def filter_out_none(original_dict):
    return {key: value for key, value in original_dict.items() if value is not None}


def transform_fields(openai_client: OpenAiClient, orig_person):
    # The model has a limited size - so we should truncate all garbage beforehand
    person = dict(orig_person)
    if "linkedin_url" in person:
        del person["linkedin_url"]
    for key, value in person.items():
        if isinstance(value, list):
            for list_index, some_dict in enumerate(value):
                # Note some_dict is just a copy
                if "linkedin_url" in some_dict:
                    # E.g. person -> list of experiences -> dict
                    del some_dict["linkedin_url"]
                person[key][list_index] = filter_out_none(some_dict)

    # Convert the JSON to a string and pass it into the prompt argument
    # TODO(peter): Do prompt engineering, clearly:
    #   * Chat-gpt is assuming nice skills like collaboration, team-work, leadership
    #   * Sometimes even makes things up - just cause Peter lives in Zurich he likes skiing
    prompt = (
        f"Input json is a persons professional experience - please summarize into the followings attributes"
        f" output as a json dictionary with the corresponding dictionary keys"
        # f" if you less than 50% sure then just output None instead of making up things"
        # TODO(pii): Try to stripe at least the basic identifiers.
        """
- get Current Organization, key = organization
- get primary industry, key = industry
- Role, key = role
- Seniority, key = seniority
- Location, key = location
- Interests in two sentences, key = interests
- Skills as up to 50 tags, key = skills
- Career next steps or needs in two sentences, key = needs
- Characteristics and personality in up to 200 words, key = character
            """
        f"Input json: {json.dumps(person)}"
    )
    raw_response = openai_client.run_prompt(prompt)
    result = gpt_response_to_json(raw_response)
    result["full_name"] = person["name"]
    return result


def strip_pii(orig_person):
    person = dict(orig_person)
    # TODO(peter): We should extend this for a bit more, like maybe organization names?
    del person["full_name"]
    return person


def evaluate_match(openai_client: OpenAiClient, orig_person1: dict, orig_person2: dict):
    # TODO(peter): Try embeddings, that should be a better way to search for alikes
    #   https://platform.openai.com/docs/guides/embeddings
    print("==========================================================")
    print(
        f"Matching {orig_person1.get('full_name')} and {orig_person2.get('full_name')}"
    )
    person1 = strip_pii(orig_person1)
    person2 = strip_pii(orig_person2)

    prompt = (
        "You are a world-class matchmaker for professionals tasked to estimate match likelihood for two individuals.\n"
        "First lets describe the input:\n"
        "The two individuals are represented as two json objects at the end of the prompt.\n"
        "We want to consider multiple prospecting relationship types listed below\n"
        "The desired output is one json map where for each relationship type between the two individuals output\n"
        "1. score (from 0 to 100) and \n"  # TODO(peter): Maybe there should be one score for each side.
        "2. reasoning which is brief three sentence explanation of the score \n\n"
        "these are relationship types to be evaluated formatted as output json key: type description "
        # individuals share ideas and experiences, foster a sense of camaraderie,
        # and support each other's professional development.
        "peer: peer camaraderie where they support each other's professional development in their industries\n"
        "recruiter: one side is looking for talent the other can provide to their company, open to work helps\n"
        # The leader provides direction and support, while the follower contributes through execution and feedback,
        # ensuring organizational success.
        "leadership: leader provides direction and support, while the follower contributes execution and feedback\n"
        "expert: expert provides one-time advice to the other side\n"
        # contract negotiator and a contractor involves ongoing dialogue, mutual agreement,
        # and conflict resolution to ensure beneficial outcomes for all parties
        "contractor: contractor provides well-scoped work for someone with a need they can fulfill\n"
        # We are in SF Bay Area, everyone is thinking about angel-investing
        "investor: investor provides capital and network which bootstraps the other sides idea \n"
        # TODO(cofounder): MAYBE
        # REMOVED(mentor): Cause usually self-served
        # the mentor imparts wisdom and guidance while the protégé absorbs and applies this knowledge,
        # fostering a cycle of growth and progression."
        # "mentor: mentor-protégé dynamic\n"
        # REMOVED(service): Cause usually self-served
        # based on consistent quality of service, mutual trust, and understanding each other's needs
        # "service: service provider and a long-term client\n"
        # REMOVED(team): GPT summaries of LI profiles were too positive on this
        # defined by a shared goal, complementary skill sets, and mutual respect,
        # leading to successful project outcomes.
        # "team: collaboration between project team members\n"
        # REMOVED(innovator): too similar to expert
        # innovator creates solutions, and the user provides feedback for improvements,
        # creating a cycle of continuous enhancement (feels similar to expert)
        # "innovator: innovator or problem solver and client or user relationship\n"
        f"and these are the two persons to evaluate match likelihood as json objects:\n{person1}\nand\n{person2}"
    )
    raw_response = openai_client.run_prompt(prompt)
    return gpt_response_to_json(raw_response)


# Matching part
# TODO(peter): There is a lot to train / experiment with here.
openai_client = open_ai_client_with_db_cache()


with open(SCRAPED_OUTPUT, "r") as handle:
    people_raw = json.load(handle)
    people_not_none = filter_out_none(people_raw)
    # For testing runtime errors, we really only need a few
    # people = slice_dictionary(people_not_none)
    people = people_not_none

    print(
        f"Loaded {len(people)} people, not-none are {len(people_not_none)} and running with {len(people)}"
    )


transformed_data = []
# load previously scraped data (which we cached last time)
if os.path.exists(TRANSFORMED_OUTPUT):
    print(f"Loading {TRANSFORMED_OUTPUT}")
    with open(TRANSFORMED_OUTPUT, "r") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            transformed_data.append(row)
else:
    # People is a dictionary
    for person in people.values():
        print(f"Summarizing {person.get('name', None)}")
        transformed_data.append(openai_client, transform_fields(person))
    # TODO: Resurrect
    # write_to_csv(transformed_data, TRANSFORMED_OUTPUT)

num_pairs = 10
n = len(transformed_data)
random_pairs = [
    (random.randint(0, n - 1), random.randint(0, n - 1)) for _ in range(num_pairs)
]
match_results = []
for pair in random_pairs:
    if pair[0] == pair[1]:
        continue
    person1 = transformed_data[pair[0]]
    person2 = transformed_data[pair[1]]
    match_result = evaluate_match(
        openai_client, orig_person1=person1, orig_person2=person2
    )
    match_results.append(
        {
            "person1": person1,
            "person2": person2,
            "result": match_result,
        }
    )


print(f"Saving sample match data to {MATCH_OUTPUT}")
with open(MATCH_OUTPUT, "w") as handle:
    json.dump(match_results, handle)
