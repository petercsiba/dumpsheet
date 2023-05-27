import requests
import openai
import re
import shutil
import time
import toml

from storage_utils import mkdir_safe

config = toml.load('secrets.toml')

openai.api_key = config["OPEN_API_KEY"]
LEAP_API_KEY = config["LEAP_API_KEY"]
MODEL_ID = "3ce1d6f0-afd1-429c-b3ec-ef76e95f87be"  # viktorio-v3
MODEL_PROMPT = "viktorio-v3"


def download_and_save_images(folder, image_urls, person):
    for index, image_url in enumerate(image_urls):
        response = requests.get(image_url, stream=True)
        response.raise_for_status()

        file_name = f"{folder}/{person.replace(' ', '_')}_{index+1}.png"
        file_name = re.sub(r'\s+', '_', file_name)  # Replace whitespace with underscores
        with open(file_name, "wb") as file:
            shutil.copyfileobj(response.raw, file)


# Function to call ChatGPT-4 API
def get_people_list():
    # Adding a bit of context on the person helps with the non-face body parts,
    # e.g. "Zuzana Caputova president of slovakia" or "Lewis Hamilton formular 1 driver"
    prompt = (
        "List presidents of European Union with as full name, president of their country name\n"
        "output as a list separated by comma remove numbers and special characters"
    )
    print(f"Running prompt {prompt}")
    model = "text-davinci-003"
    response = openai.Completion.create(
        engine=model,
        prompt=prompt,
        max_tokens=500,
        n=1,
        stop=None,
        temperature=0.7,
    )
    print(f".. given response {response.choices[0]}")

    # list separated by comma without numbers
    return response.choices[0].text.strip().split(", ")


# Function to call the image generation API
def generate_images(prompt, negative_prompt=""):
    print(f"generate_images {prompt}")
    url = f"https://api.tryleap.ai/api/v1/images/models/{MODEL_ID}/inferences"

    payload = {
        "prompt": f"{prompt}",
        "negativePrompt": negative_prompt,
        "steps": 60,  # For caricatures gets more believable faces, trading off for mutations
        "width": 512,  # keep same as model
        "height": 512,
        "numberOfImages": 6,
        # Generally for caricatures felt like higher temp is better
        # TOO MUCH led to too digital/smooth-ish images, sometimes weird mutations
        # TOO little got too real, with colors included and such
        "promptStrength": 8,
        # Same seed should further help generating with the same style
        # BUT no seed helps to find the best seed for that style :D
        # 2835452228 is from inference 5019d784-6f42-4d45-8cb7-d3ead2d44f22
        # "seed": 2835452228,
        "enhancePrompt": False,
        "upscaleBy": "x1",  # upscale keep1, for fine-tuned model works best (can tile, or do weird stuff)
        "sampler": "ddim"
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {LEAP_API_KEY}" 
    }

    response = requests.post(url, json=payload, headers=headers)
    return response.json()


def get_image_urls_for_inference(inference_id):
    url = f"https://api.tryleap.ai/api/v1/images/models/{MODEL_ID}/inferences/{inference_id}"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {LEAP_API_KEY}"
    }

    img_response = requests.get(url, headers=headers)
    img_data = img_response.json()
    return [img["uri"] for img in img_data["images"]]


def fix_shit(people):
    inference_ids = ['6c349c15-ad6a-4057-8e82-d62c09dd6108', 'e0096b51-c0de-466c-8392-f4305269694b', '9ccbff11-5373-49ce-9530-50251390663a', '3ddb0806-290c-4ef8-87ea-379c1d664036', 'eec9e0b1-1dbf-46a5-a102-42d7cf8132dc', '88c4286e-53b6-46e1-a319-7bd31d3ebd3c', 'f0397fec-a4f4-41e9-a0c3-eca8eb7b122d', 'd69ea48d-ec35-4300-8520-275e9e314d68', 'fc808b13-82ef-40b6-b652-05433e97d78c', '902262bc-4c06-440d-9ad1-3d96f837b016', '42381f50-42dd-428d-8557-e1f0a764835e', '20657004-4dc1-4b00-bb36-0edf335407e0', '6ac0174d-0ece-4061-a66a-58b4c23ae99c', '975263a0-94b4-4247-8f8f-9398bb6d9658', 'dbcdc0f5-74e9-433e-b9ee-15bd883bd415', 'd7c33c9e-ebc0-4869-a31a-5d6f09634d08', '9845d211-58d9-406b-b5aa-7c7869def8ec', 'd7b301d1-8a2e-4b1f-9dcc-3210b6e6cde2', '60fc9654-bb76-48eb-a316-6c171eb7e352', '04476928-40d0-4288-9cdb-8035feb63818', '33f2df24-0372-452b-aaeb-ef6209455e51', '6a51194b-26ec-4fae-87c4-55cdac4aaeae', '9bd97b14-7c89-4b6c-a9fe-e0f720eca995', '59336d8e-c899-425a-b435-57e2039c8c77', '968f28f4-c2d9-4f90-8c91-06032f4150f5', '37c8e3dc-2721-42f7-ac5f-7bcc7675cdb9', 'f2aab977-b5b4-4d34-9daa-6cd3a0899bd5']
    folder = f"images-{inference_ids[0]}"
    mkdir_safe(folder)

    for (inference_id, person) in zip(inference_ids, people):
        print(inference_id, person)
        image_urls = get_image_urls_for_inference(inference_id)
        print(image_urls)
        download_and_save_images(folder, image_urls, person)


# Main function to call both APIs and store responses in a list
def main():
    # fix_shit()
    # return
    # people = get_people_list()
    people = [
        'Alexander Van der Bellen, President of Austria',
        'Rumen Radev, President of Bulgaria',
        'Zuzana Čaputová, President of Slovakia',
        'Kolinda Grabar-Kitarović, President of Croatia',
        'Nicos Anastasiades, President of Cyprus',
        'Miloš Zeman, President of Czech Republic',
        'Margrethe II, Queen of Denmark',
        'Kersti Kaljulaid, President of Estonia',
        'Sauli Niinistö, President of Finland',
        'Emmanuel Macron, President of France',
        'Frank-Walter Steinmeier, President of Germany',
        'Katerina Sakellaropoulou, President of Greece',
        'Michael D. Higgins, President of Ireland',
        'Sergio Mattarella, President of Italy',
        'Raimonds Vējonis, President of Latvia',
        'Gitanas Nausėda, President of Lithuania',
        'Henri, Grand Duke of Luxembourg',
        'Zoran Milanović, President of Croatia',
        'Klaus Iohannis, President of Romania',
        'Egils Levits, President of Latvia',
        'Aleksander Kwaśniewski (Acting), President of Poland',
        'Marcelo Rebelo de Sousa, President of Portugal',
        'János Áder, President of Hungary',
        'Borut Pahor, President of Slovenia',
        'Felipe VI, King of Spain',
        'Carl XVI Gustaf, King of Sweden',
        'Elizabeth II, Queen of the United Kingdom'
    ]
    print(people)

    responses = []
    for person in people:
        #prompt = f"picture of {person} {MODEL_PROMPT}, full body"
        # prompt = f"a caricature of {person} {MODEL_PROMPT}, headshot, profile, slightly smiling, intricate hair"
        # TODO(peter): Try promptperfect.jina.ai
        # Elderly man caricature with exaggerated features, deep wrinkles, large nose and ears, humorous expression | fusion of Charlie Chaplin and Salvador Dali personas | tailored suit with bow tie, surrealist elements in attire and accessories | mixed media: watercolor and ink technique emulation | evoke emotion, intrigue, humor | detailed facial expressions and clothing textures | 4k resolution for crisp visuals
        prompt = (
            f"a caricature drawing of {person} {MODEL_PROMPT}, headshot, profile, slightly smiling, "
            f"lines, intricate hair, fits in frame, crosshatching, textured, fine strokes"
        )
        negative_prompt = (
            "duplicate, malformed, color, mutated, jpeg artifacts, out of frame, digital, smooth"
        )
        response = generate_images(
            prompt=prompt,
            negative_prompt=negative_prompt,
        )
        print(response)
        response["person"] = person # piggyback this data
        responses.append(response)
        # break # For testing

    inference_ids = [r["id"] for r in responses]
    print(f"INFERENCE IDS: {inference_ids}")
    folder = f"images-{inference_ids[0]}"
    mkdir_safe(folder)

    # Generating the images takes some time
    time.sleep(180)

    for response in responses:
        inference_id = response["id"]
        image_urls = get_image_urls_for_inference(inference_id)
        print(image_urls)
        download_and_save_images(folder, image_urls, response["person"])

    return responses


if __name__ == "__main__":
    main()