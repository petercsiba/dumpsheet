import json
import openai
import pprint
import re
import time

# TODO(P0, devx): Make it class, add a caching layer with DynamoDB (more robust testing, faster prod re-runs).
#   * After that we can also easily collect total tokens used and such.

pp = pprint.PrettyPrinter(indent=4)


class Timer:
    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.start_time = time.time()

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_time = time.time() - self.start_time
        print("{}: {:.2f} seconds".format(self.label, elapsed_time))


def truncate_string(input_string):
    truncated_string = input_string[:500]

    # Append "(truncated)" if the string is longer
    if len(input_string) > 500:
        truncated_string += " ... (truncated for logging readability)"
    return truncated_string


# model = gpt-4, gpt-4-0314, gpt-4-32k, gpt-4-32k-0314, gpt-3.5-turbo, gpt-3.5-turbo-0301
# For gpt-4 you need to be whitelisted.
# About 0.4 cents per request (about 2000 tokens). Using gpt-4 would be 15x more expensive :/
# TODO(peter): Do sth about max prompt length (4096 tokens INCLUDING the generated response)
# TODO(peter, fine-tune): Feels like for repeated tasks it would be great to speed up and/or cost save
#   https://platform.openai.com/docs/guides/fine-tuning/advanced-usage
# TODO(peter): We should templatize the prompt into "function body" and "parameters";
#   then we can re-use the "body" to "fine-tune" a model and have faster responses.
def run_prompt(prompt: str, model="gpt-3.5-turbo", retry_timeout=60, print_prompt=True):
    # wait is too long so carry one
    if retry_timeout > 600:
        return '{"error": "timeout ' + str(retry_timeout) + '"}'
    if print_prompt:
        # print(f"Asking {model} for: {truncate_string(prompt)}")
        loggable_prompt = prompt.replace('\n', ' ')
        print(f"Asking {model} for: {loggable_prompt}")
    with Timer("ChatCompletion"):
        # TODO: My testing on gpt-4 through the browswer gives better results
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "system", "content": prompt}]
            )
        # openai.error.RateLimitError: That model is currently overloaded with other requests.
        # You can retry your request, or contact us through our help center at help.openai.com if the error persists.
        # (Please include the request ID 7ed28a69c5cda5378f57266336539b7d in your message.)
        except openai.error.RateLimitError as err:
            print(f"Got RATE-LIMITED!!! Sleeping for {retry_timeout}. Raw error: {err}")
            time.sleep(retry_timeout)
            return run_prompt(prompt, model, 2 * retry_timeout)  # exponential backoff
    print(f"Token usage {json.dumps(response['usage'])}")
    return response.choices[0].message.content.strip().replace("\n", "")


def get_first_occurrence(s: str, list_of_chars: list):
    first_occurrence = len(s)  # initialize to length of the string

    for char in list_of_chars:
        index = s.find(char)
        if index != -1 and index < first_occurrence:  # update if char found and it's earlier
            first_occurrence = index

    if first_occurrence == len(s):
        return -1


def gpt_response_to_json(raw_response: str, debug=True):
    if raw_response is None:
        if debug:
            print("raw_response is None")
        return None
    wrong_input_responses = [
        "Sorry, it is not possible to create a json dict",
        "Sorry, as an AI language model"
    ]
    if any(raw_response.startswith(s) for s in wrong_input_responses):
        if debug:
            print(f"WARNING: Likely provided wrong input as GPT is complaining with {raw_response}")
        return None

    orig_response = raw_response
    # For "Expecting property name enclosed in double quotes"
    # Obviously not bullet-proof for stuff like 'Ed's', can be probably
    # raw_json = raw_response.replace("'", '"')
    # GPT to rescue: Use regex to replace single quotes with double quotes
    # raw_response = re.sub(r"\'((?:[^']|(?<=\\\\)')*?[^'])\'", r'"\1"', raw_response)
    # Welp - OMG this from PPrint :facepalm:
    raw_response = raw_response.replace("{'", '{"').replace("':", '":').replace(", '", ', "')
    raw_response = raw_response.replace("',", '",').replace(": '", ': "').replace("'}", '"}')
    raw_response = raw_response.replace(': ""', ': "').replace('""}', '"}')
    # Sometimes GPT adds the extra comma, well, everyone is guilty of that leading to a production outage so :shrug:
    # Examples: """her so it was cool",    ],"""
    raw_response = re.sub(r'",\s*\]', '"]', raw_response)
    raw_response = re.sub(r'",\s*\}', '"}', raw_response)
    raw_response = re.sub(r'\],\s*\}', ']}', raw_response)
    raw_response = re.sub(r'\],\s*\]', ']]', raw_response)
    raw_response = re.sub(r'\},\s*\}', '}}', raw_response)
    raw_response = re.sub(r'\},\s*\]', '}]', raw_response)
    if debug:
        print(f"converted {orig_response}\n\nto\n\n{raw_response}")
    try:
        # The model might have just crafted a valid json object
        result = json.loads(raw_response)
    except json.decoder.JSONDecodeError as orig_err:
        # In case there is something before the actual json output
        start_index = get_first_occurrence(raw_response, ['{', '['])
        raw_json = raw_response[start_index:]  # -1 works
        # TODO(P2, devx): Handle the case when there is clearly NO json response.
        #   Like these can be "-" separated into a list  - Catalina: girl from Romania- Car reselling guy: fro
        #   NOTE: Figure out if this uses spaces or not.
        if debug and len(raw_json) * 2 < len(raw_response):
            print(f"WARNING: Likely the GPT response is NOT a JSON:\n{raw_json}\nresulted from\n{orig_response}")
        try:
            result = json.loads(raw_json)
        except json.decoder.JSONDecodeError as sub_err:
            if debug:
                print(
                    f"Could NOT decode json cause SUB ERROR: {sub_err} for raw_reponse "
                    f"(note does a bunch of replaces) {raw_response}. ORIGINAL ERROR: {orig_err}"
                )
            return None
    return result


# When you expect a string, but you don't quite get it such from chat-gpt.
# Output just raw text, without braces, bullet points.
def gpt_response_to_plaintext(raw_response) -> str:
    if raw_response is None:
        return "None"
    try:
        json_response = gpt_response_to_json(raw_response, debug=False)
        if json_response is None:
            return str(raw_response)

        if isinstance(json_response, list):
            return " ".join([str(x) for x in json_response])
        # TypeError: sequence item 0: expected str instance, dict found
        if isinstance(json_response, dict):
            items = []
            for key, value in json_response.items():
                items.append(f"{key}: {value}")
            return " ".join([str(x) for x in items])
        # TODO(P2): Implement more fancy cases, nested objects and such.
        return str
    except Exception:
        return str(raw_response)
    # Maybe it's a JSON
