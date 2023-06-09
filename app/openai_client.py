import json
import hashlib
import openai
import re
import time

from dataclasses import dataclass, field
from dynamodb import DynamoDBManager, write_data_class, read_data_class
from typing import Optional, List

openai.api_key = "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"


def truncate_string(input_string):
    truncated_string = input_string[:500]

    # Append "(truncated)" if the string is longer
    if len(input_string) > 500:
        truncated_string += " ... (truncated for logging readability)"
    return truncated_string


@dataclass
class PromptStats:
    request_time_ms: int = 0  # in milliseconds
    prompt_tokens: int = 0
    completion_tokens: int = 0

    total_requests: int = 0
    total_tokens: int = 0

    # TODO(P2, fun): Might be cool to translate it to dollars, I guess one-day usage based billing.
    def pretty_print(self):
        return (
            f"{self.total_requests} queries to ChatGPT using {self.total_tokens} tokens "
            f"in {self.request_time_ms/1000:.2f} seconds total query time."
        )


# Also DynamoDB table
@dataclass
class PromptLog:
    # The maximum size of a primary key (partition key and sort key combined) is 2048 bytes
    prompt_hash: str
    model: str

    prompt: str
    result: str = None
    # OMG DynamoDB and floats
    request_time_ms: int = 0  # in milliseconds
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    # Cannot over-ride the default init method as that's used by my custom DynamoDB driver.
    @staticmethod
    def create(prompt, model):
        return PromptLog(
            prompt = prompt,
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest(),
            model = model
        )


class OpenAiClient:
    def __init__(self, dynamodb: Optional[DynamoDBManager]):
        self.prompt_cache_table = dynamodb.create_prompt_table_if_not_exists() if bool(dynamodb) else None
        # In-memory representation of the above to mostly sum up stats.
        self.prompt_stats: List[PromptLog] = field(default_factory=list)

    def sum_up_prompt_stats(self) -> PromptStats:
        result = PromptStats()
        for prompt_log in self.prompt_stats:
            result.prompt_tokens += prompt_log.prompt_tokens
            result.completion_tokens += prompt_log.completion_tokens
            result.request_time_ms = prompt_log.request_time_ms

        result.total_requests = len(self.prompt_stats)
        result.total_tokens = result.prompt_tokens + result.completion_tokens
        return result

    def _run_prompt(self, prompt: str, model="gpt-3.5-turbo", retry_timeout=60):
        # wait is too long so carry on
        if retry_timeout > 600:
            print("ERROR: waiting for prompt too long")
            return None

        # TODO(P1, ux): My testing on gpt-4 through the browswer gives better results
        #  - get access and use it on drafts.
        try:
            # TODO(P2, devx): This can get stuck-ish, we should handle that somewhat nicely.
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "system", "content": prompt}]
            )
        # openai.error.RateLimitError: That model is currently overloaded with other requests.
        # You can retry your request, or contact us through our help center at help.openai.com
        # if the error persists.
        # (Please include the request ID 7ed28a69c5cda5378f57266336539b7d in your message.)
        except openai.error.RateLimitError as err:
            print(f"Got RATE-LIMITED!!! Sleeping for {retry_timeout}. Raw error: {err}")
            time.sleep(retry_timeout)
            return self._run_prompt(prompt, model, 2 * retry_timeout)  # exponential backoff

        return response

    # model = gpt-4, gpt-4-0314, gpt-4-32k, gpt-4-32k-0314, gpt-3.5-turbo, gpt-3.5-turbo-0301
    # For gpt-4 you need to be whitelisted.
    # About 0.4 cents per request (about 2000 tokens). Using gpt-4 would be 15x more expensive :/
    # TODO(peter): Do sth about max prompt length (4096 tokens INCLUDING the generated response)
    # TODO(peter, fine-tune): Feels like for repeated tasks it would be great to speed up and/or cost save
    #   https://platform.openai.com/docs/guides/fine-tuning/advanced-usage
    # TODO(peter): We should templatize the prompt into "function body" and "parameters";
    #   then we can re-use the "body" to "fine-tune" a model and have faster responses.
    def run_prompt(self, prompt: str, model="gpt-3.5-turbo", print_prompt=True):
        prompt_log = PromptLog.create(prompt=prompt, model=model)

        if print_prompt:
            loggable_prompt = prompt.replace('\n', ' ')
            print(f"Asking {model} for: {loggable_prompt}")

        if bool(self.prompt_cache_table):
            key = PromptLog.create(prompt, model)
            cached_prompt: PromptLog = read_data_class(data_class_type=PromptLog, table=self.prompt_cache_table, key={
                'prompt_hash': key.prompt_hash,
                'model': key.model,
            }, print_not_found=True)
            if bool(cached_prompt):
                print("cached_prompt: serving out of cache")
                if cached_prompt.prompt != prompt:
                    print(f"ERROR: hash collision for {key.prompt_hash} for prompt {prompt}")
                else:
                    self.prompt_stats.append(cached_prompt)
                    return cached_prompt.result

        start_time = time.time()
        # ====== ACTUAL LOGIC, everything else is monitoring, caching and analytics.
        response = self._run_prompt(prompt, model)

        prompt_log.request_time_ms = int(1000 * (time.time() - start_time))
        print(f"ChatCompletion: { prompt_log.request_time_ms / 1000} seconds")  # Note, includes retry time.

        if response is None:
            return None
        result = response.choices[0].message.content.strip().replace("\n", "")

        token_usage = response['usage']
        prompt_log.result = result
        prompt_log.prompt_tokens = token_usage.get("prompt_tokens", 0)
        prompt_log.completion_tokens = token_usage.get("completion_tokens", 0)
        self.prompt_stats.append(prompt_log)
        print(f"Token usage {json.dumps(token_usage)}")

        # Log and cache the result
        if bool(self.prompt_cache_table):
            write_data_class(self.prompt_cache_table, prompt_log)
            print("cached_prompt: written to cache")
        return result


def get_first_occurrence(s: str, list_of_chars: list):
    first_occurrence = len(s)  # initialize to length of the string

    for char in list_of_chars:
        index = s.find(char)
        if index != -1 and index < first_occurrence:  # update if char found and it's earlier
            first_occurrence = index

    if first_occurrence == len(s):
        return -1


def gpt_response_to_json(raw_response: Optional[str], debug=True):
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
    # TODO(P2, devx): Redundant character escape
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
    except Exception:
        pass

    return str(raw_response)
