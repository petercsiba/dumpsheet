# TODO(P1, devx): Make it work
import ast
import json
import os.path
from typing import Any, List, Type

import numpy as np
import pandas as pd
from openai.embeddings_utils import cosine_similarity

from app.datashare import DataEntry, PersonDataEntry, dict_to_dataclass
from app.dynamodb import parse_dynamodb_json
from common.openai_client import OpenAiClient

MIN_TEXT_CHAR_LENGTH = 100

# Research list:
# Extraction:
# * Named Entity Recognition (NER)
# Aggregation:
# * To represent an entire paragraph as one vector, several methods:
# * * averaging, max pooling, CLS / BERT
# For locally running the models we might be just able to; TLDR everything looks to generic, specialized is our way.
# * Hugging Face Transformers Python library (pip install transformers)
# * Facebook Faiss (vector DB)
# * Pinecone, a fully managed vector database
# * Weaviate, an open-source vector search engine
# * Redis as a vector database
# * Qdrant, a vector search engine
# * Milvus, a vector database built for scalable similarity search
# * Cohere, https://docs.pinecone.io/docs/cohere
# * LangChain (i really don't get it), https://www.pinecone.io/learn/langchain/
# * Chroma, an open-source embeddings store
# * Typesense, fast open source vector search
# * Zilliz, data infrastructure, powered by Milvus
# * https://github.com/pgvector/pgvector: SELECT * FROM items ORDER BY embedding <-> '[3,1,2]' LIMIT 5;


def load_csv_to_dataclass(data_class_type: Type[Any], csv_filepath: str) -> List[Any]:
    # Load the CSV file to a DataFrame
    loaded_df = pd.read_csv(csv_filepath)
    print(f"Loading {csv_filepath} found columns {loaded_df.columns}")

    # Initialize an empty list to store the dataclass instances
    data_entries = []

    # Iterate over each row in the DataFrame
    for _, row in loaded_df.iterrows():
        row_dict = row.to_dict()
        print(f"row_dict {row_dict}")
        # Convert any JSON strings in the row to Python objects
        for key, value in row_dict.items():
            if isinstance(value, str):
                try:
                    # Try to load JSON
                    loaded_json = json.loads(value)
                    # If loading succeeds, then parse the DynamoDB JSON format
                    row_dict[key] = parse_dynamodb_json(loaded_json)
                except json.JSONDecodeError:
                    pass  # Not a JSON string, leave as is

        data_entry = dict_to_dataclass(row_dict, data_class_type)
        data_entries.append(data_entry)

    # Return the list of dataclass instances
    print(f"Parsed {len(data_entries)} items of {data_class_type} from {csv_filepath}")
    return data_entries


# Define a function to get the N most similar people
def get_most_similar(df, person_embedding, n=2):
    # This might just over-write the stuff lol? Ok lets go!
    # NOTE: We do reshape cause ValueError: shapes (1,1536) and (1,1536) not aligned
    #   I GUESS that to output one number, we should have (1,1536) and (1536, 1), otherwise we get (1536, 1536)
    search_vector = np.array(person_embedding).reshape(-1, 1)
    df["similarities"] = df["ada_embedding"].apply(
        lambda x: cosine_similarity(np.array(x).reshape(1, -1), search_vector)
    )
    most_similar_df = df.sort_values("similarities", ascending=False).head(
        n + 1
    )  # n+1 because the person is most similar to themselves

    # We're using `.item()` to get the value of the similarity as a float, because it's originally in a 1-element list.
    # If this gives an error because the values are not 1-element lists, you can remove the `.item()` call.
    most_similar_df["similarities"] = most_similar_df["similarities"].apply(
        lambda x: x[0].item()
    )
    return most_similar_df[1:]  # exclude the person themselves


def create_embeddings(csv_filepath, output_filepath):
    all_data_entries = load_csv_to_dataclass(DataEntry, csv_filepath)
    list_of_lists = [de.output_people_entries for de in all_data_entries]
    all_people_entries: List[PersonDataEntry] = [
        item for sublist in list_of_lists for item in sublist
    ]  # GPT generated no idea how it works

    print("==== ALL PEOPLE entries ====")
    # print(all_people_entries)

    people = []
    for person in all_people_entries:
        text = person.get_transcript_text()
        if person.parsing_error or len(text) < MIN_TEXT_CHAR_LENGTH:
            print(
                f"Skipping {person.name} cause too little data on them OR input parse error occurred"
            )
            continue

        people.append(
            {
                "name": person.name,
                "text": text,
                "ada_embedding": openai_client.get_embedding(text=text),
            }
        )

    print(f"Got {len(people)} embeddings creating dataframe with the vectors")
    people_df = pd.DataFrame(people)
    people_df.to_csv(output_filepath, index=False)
    return people_df


def craft_intro_message(client: OpenAiClient, person1, person2) -> str:
    query = """I would like to introduce {} to {} to each other - cause they seem to have similarities in common.
Please generate a short intro message (up to 250 characters)
written in style of a "smooth casual friendly yet professional person",
ideally adjusted to the talking style from my notes.
Please make sure that:
* to mention what I enjoyed OR appreciated in the conversation
* include a fact / a hobby / an interest from our conversation
* omit any sensitive information, especially money, race or origin
Only output the resulting message - do not use double quotes at all.

My notes on are:
* {}: {}
and
* {}: {}
""".format(
        person1["name"],
        person2["name"],
        person1["name"],
        person1["text"],
        person2["name"],
        person2["text"],
    )
    return client.run_prompt(query, print_prompt=False)


if __name__ == "__main__":
    openai_client = OpenAiClient(dynamodb=None)

    filepath = "test/katka-data-entries.csv"
    embed_filepath = filepath + ".embedded"
    if os.path.exists(embed_filepath):
        print(f"Reading from existing embedding filepath {embed_filepath}")
        people_df = pd.read_csv(embed_filepath)
        # If this column contains complex data types like lists or arrays,
        # they are converted to string representation when saving to a CSV file.
        # When you load the CSV file back into pandas, these complex types remain as strings.
        people_df["ada_embedding"] = people_df["ada_embedding"].apply(ast.literal_eval)
    else:
        people_df = create_embeddings(filepath, embed_filepath)

    # Verify the content of the 'ada_embedding' column
    # print(f"Embedding type {type(people_df['ada_embedding'].iloc[0])}")

    # Iterate over each person in the dataframe
    all_intros = []
    for index, person in people_df.iterrows():
        # Get the three most similar people
        most_similar_people = get_most_similar(people_df, person["ada_embedding"], 3)

        print(f"========= Most similar to {person['name']} ===========")
        most_similar_people = most_similar_people[
            most_similar_people["similarities"] > 0.8
        ]

        # If the DataFrame is not empty, print it
        if most_similar_people.empty:
            continue

        intro_candidate = most_similar_people[
            most_similar_people["similarities"] > 0.87
        ].head(1)
        if not intro_candidate.empty:
            candidate = intro_candidate.iloc[0]
            print(
                f"Found a good intro candidate {candidate['name']}, lets generate the intro message"
            )
            intro = craft_intro_message(openai_client, person, candidate)
            all_intros.append(f"{person['name']} to {candidate['name']}: {intro}")
            print(intro)

        # Drop returns a copy
        print(most_similar_people.drop("ada_embedding", axis=1))
        reminder = person["text"][:100].replace("\n", " ")
        print(f"({reminder})")

    print(f"=========== ALL INTRO {len(all_intros)} ============")
    print("\n\n".join(all_intros))
