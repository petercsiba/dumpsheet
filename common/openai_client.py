# TODO(P0, devx, quality): Update chat-gpt model usage, ideally use those functions too!
#  * https://platform.openai.com/docs/guides/gpt/function-calling
#   Define a function called
#       extract_people_data(people: [
#           {name: string, birthday: string, location: string}
#       ]), to extract all people mentioned in a Wikipedia article.
# TODO(P1, devx): This Haystack library looks quite good https://github.com/deepset-ai/haystack
# TODO(P3, research, fine-tune): TLDR; NOT worth it. Feels like for repeated tasks it would be great to
#  speed up and/or cost save https://platform.openai.com/docs/guides/fine-tuning/advanced-usage
import json
import hashlib
import openai
import re
import tiktoken
import time

from dataclasses import dataclass
from typing import Optional, List

from app.dynamodb import DynamoDBManager, write_data_class, read_data_class
from common.config import OPEN_AI_API_KEY
from common.storage_utils import get_fileinfo
from common.utils import Timer

# TODO(P1, specify organization id): Header OpenAI-Organization
openai.api_key = OPEN_AI_API_KEY
# https://platform.openai.com/docs/models/gpt-4
DEFAULT_MODEL = "gpt-4-0613"  # Thanks Vishal
# Sometimes seems the newest models experience downtime-so try to backup.
BACKUP_MODEL = "gpt-3.5-turbo"
BACKUP_MODEL_AFTER_NUM_RETRIES = 3
# DEFAULT_MODEL = "gpt-3.5-turbo-0613"
test_transcript = None


def truncate_string(input_string):
    truncated_string = input_string[:500]

    # Append "(truncated)" if the string is longer
    if len(input_string) > 500:
        truncated_string += " ... (truncated for logging readability)"
    return truncated_string


def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    # https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
    # Encoding name	OpenAI models
    # cl100k_base	gpt-4, gpt-3.5-turbo, text-embedding-ada-002
    # p50k_base	Codex models, text-davinci-002, text-davinci-003
    # r50k_base (or gpt2)	GPT-3 models like davinci
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


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
            f"{self.total_requests} queries to LLMs ({self.total_tokens} tokens) "
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
        print("OpenAiClient init")
        self.prompt_cache_table = dynamodb.create_prompt_table_if_not_exists() if bool(dynamodb) else None
        # In-memory representation of the above to mostly sum up stats.
        self.prompt_stats: List[PromptLog] = []

    def sum_up_prompt_stats(self) -> PromptStats:
        stats = PromptStats()
        for prompt_log in self.prompt_stats:
            stats.prompt_tokens += prompt_log.prompt_tokens
            stats.completion_tokens += prompt_log.completion_tokens
            stats.request_time_ms += prompt_log.request_time_ms

        stats.total_requests = len(self.prompt_stats)
        stats.total_tokens = stats.prompt_tokens + stats.completion_tokens
        return stats

    def _run_prompt(self, prompt: str, model=DEFAULT_MODEL, retry_timeout=10, retry_num=0):
        # wait is too long so carry on
        if retry_timeout > 300:
            print("ERROR: waiting for prompt too long")
            return None
        if retry_num >= BACKUP_MODEL_AFTER_NUM_RETRIES and model != BACKUP_MODEL:
            print(f"WARNING: Changing model from {model} to {BACKUP_MODEL} after {retry_num} retries")
            # The "cutting-edge" models experience more downtime.
            model = BACKUP_MODEL

        # TODO(P1, ux): My testing on gpt-4 through the browser gives better results
        #  - get access and use it on drafts.
        response = None
        should_retry = False
        try:
            # TODO(P2, devx): This can get stuck-ish, we should handle that somewhat nicely.
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "system", "content": prompt}]
                # functions = functions
            )
        # openai.error.RateLimitError: That model is currently overloaded with other requests.
        # You can retry your request, or contact us through our help center at help.openai.com
        # if the error persists.
        # (Please include the request ID 7ed28a69c5cda5378f57266336539b7d in your message.)
        except (openai.error.RateLimitError, openai.error.Timeout, openai.error.TryAgain) as err:
            print(f"Got time-based {type(err)} error - sleeping for {retry_timeout} cause {err}")
            should_retry = True
            time.sleep(retry_timeout)
        # Their fault
        except (openai.error.APIError, openai.error.ServiceUnavailableError) as err:
            print(f"Got server-side {type(err)} error - sleeping for {retry_timeout} cause {err}")
            should_retry = True
            time.sleep(retry_timeout)
        # Our fault
        except (openai.error.InvalidRequestError, openai.error.InvalidAPIType, openai.error.AuthenticationError) as err:
            print(f"Got client-side {type(err)} error - we messed up so lets rethrow this error {err}")
            raise err

        if should_retry:
            return self._run_prompt(prompt, model, 2 * retry_timeout, retry_num=retry_num+1)  # exponential backoff

        return response

    # About 0.4 cents per request (about 2000 tokens). Using gpt-4 would be 15x more expensive :/
    # TODO(peter): Do sth about max prompt length (4096 tokens INCLUDING the generated response)
    # TODO(P1, devx): We should templatize the prompt into "function body" and "parameters";
    #   then we can re-use the "body" to "fine-tune" a model and have faster responses.
    def run_prompt(self, prompt: str, model=DEFAULT_MODEL, print_prompt=True):
        prompt_log = PromptLog.create(prompt=prompt, model=model)

        if print_prompt:
            loggable_prompt = prompt.replace('\n', ' ')
            print(f"Asking {model} for: {loggable_prompt}")

        key = PromptLog.create(prompt, model)
        if bool(self.prompt_cache_table):
            cached_prompt: PromptLog = read_data_class(data_class_type=PromptLog, table=self.prompt_cache_table, key={
                'prompt_hash': key.prompt_hash,
                'model': key.model,
            }, print_not_found=False)
            if bool(cached_prompt):
                print("cached_prompt: servifsdfng out of cache")
                if cached_prompt.prompt != prompt:
                    print(f"ERROR: hash collision for {key.prompt_hash} for prompt {prompt}")
                else:
                    self.prompt_stats.append(cached_prompt)
                    return cached_prompt.result

        start_time = time.time()
        # ====== ACTUAL LOGIC, everything else is monitoring, caching and analytics.
        response = self._run_prompt(prompt, model)

        prompt_log.request_time_ms = int(1000 * (time.time() - start_time))
        if print_prompt:
            print(f"ChatCompletion: { prompt_log.request_time_ms / 1000} seconds")  # Note, includes retry time.

        if response is None:
            return None
        # TODO(P2, test): There used to be new-line replacement, imho more confusing than useful.
        gpt_result = response.choices[0].message.content.strip()

        token_usage = response['usage']
        prompt_log.result = gpt_result
        prompt_log.prompt_tokens = token_usage.get("prompt_tokens", 0)
        prompt_log.completion_tokens = token_usage.get("completion_tokens", 0)
        self.prompt_stats.append(prompt_log)
        if print_prompt:
            print(f"Token usage {json.dumps(token_usage)}")

        # Log and cache the result
        if bool(self.prompt_cache_table):
            write_data_class(self.prompt_cache_table, prompt_log)
            print(f"cached_prompt: written to cache {key.prompt_hash}")
        return gpt_result

    # They claim to return 1536 dimension of normalized to 1 (cosine or euclid returns same)
    # TODO(P0, quality): There are a LOT of unknowns here for me:
    #   * How it works with larger texts?
    #   * What is LangChan good for? It feels just like a layer on top of (OpenAI) models.
    #   * How the to event store this in DynamoDB? Probably gonna go with Pinecode or similar from the beginning.
    def get_embedding(self, text, model="text-embedding-ada-002"):
        text = text.replace("\n", " ")
        print(f"Running embedding for {num_tokens_from_string(text)} token of text {text[:100]}")
        with Timer("Embedding"):
            embedding = openai.Embedding.create(input=[text], model=model)['data'][0]['embedding']
            # print(f"Embedding: {embedding}")
            return embedding

    # TODO(P1, Facebook MMS): Better multi-language support, Slovak was OK, but it got some things quite wrong.
    #   * https://about.fb.com/news/2023/05/ai-massively-multilingual-speech-technology/
    #   We might need to run the above ourselves for now (BaseTen hosting?)
    #   For inspiration on how to run Whisper locally:
    #   * https://towardsdatascience.com/whisper-transcribe-translate-audio-files-with-human-level-performance-df044499877
    # They claim to have WER <50% for these:
    # Afrikaans, Arabic, Armenian, Azerbaijani, Belarusian, Bosnian, Bulgarian, Catalan, Chinese, Croatian, Czech,
    # Danish, Dutch, English, Estonian, Finnish, French, Galician, German, Greek, Hebrew, Hindi, Hungarian, Icelandic,
    # Indonesian, Italian, Japanese, Kannada, Kazakh, Korean, Latvian, Lithuanian, Macedonian, Malay, Marathi, Maori,
    # Nepali, Norwegian, Persian, Polish, Portuguese, Romanian, Russian, Serbian, Slovak, Slovenian, Spanish, Swahili,
    # Swedish, Tagalog, Tamil, Thai, Turkish, Ukrainian, Urdu, Vietnamese, and Welsh.
    # TODO(P1, devx): Maybe better place in openai_utils
    def transcribe_audio(self, audio_filepath):
        if test_transcript is not None:
            return test_transcript

        prompt_hint = "these are notes from an event I attended describing the people I met, my impressions and actions"

        # (2023, May): File uploads are currently limited to 25 MB and the following input file types are supported:
        #   mp3, mp4, mpeg, mpga, m4a, wav, and webm (MAYBE fake news)
        # TODO(P2, feature); For longer inputs, we can use pydub to chunk it up
        #   https://platform.openai.com/docs/guides/speech-to-text/longer-inputs
        with open(audio_filepath, "rb") as audio_file:
            print(f"Transcribing (and translating) {get_fileinfo(file_handle=audio_file)}")
            # Data submitted through the API is no longer used for service improvements (including model training)
            #   unless the organization opts in
            # https://openai.com/blog/introducing-chatgpt-and-whisper-apis
            with Timer("Audio transcribe (and maybe translate)"):
                # NOTE: Verified that for English there is no difference between "transcribe" and "translate",
                # by changing it locally and seeing the translate is "cached_prompt: serving out of cache".
                transcript = openai.Audio.translate(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json",
                    # language="en",  # only for openai.Audio.transcribe
                    prompt=prompt_hint,
                    # If set to 0, the model will use log probability to automatically increase the temperature
                    #   until certain thresholds are hit.
                    temperatue=0,
                )
                result = transcript["text"]
                print(f"Transcript: {result}")
                return result


def _get_first_occurrence(s: str, list_of_chars: list):
    first_occurrence = len(s)  # initialize to length of the string

    for char in list_of_chars:
        index = s.find(char)
        if index != -1 and index < first_occurrence:  # update if char found and it's earlier
            first_occurrence = index

    if first_occurrence == len(s):
        return -1
    return first_occurrence


def _get_last_occurrence(s: str, list_of_chars: list):
    last_occurrence = -1  # initialize to -1 as a "not found" value

    for char in list_of_chars:
        index = s.rfind(char)
        if index > last_occurrence:  # update if char found and it's later
            last_occurrence = index

    return last_occurrence


def _try_decode_non_json(raw_response: str):
    # Sometimes it returns a list of strings in format of " -"
    lines = raw_response.split("\n")
    if len(lines) > 1:
        bullet_point_lines = sum(s.lstrip().startswith('-') for s in lines)
        if bullet_point_lines + 1 >= len(lines):
            print(f"Most of lines {bullet_point_lines} out of {len(lines)} start as a bullet point, assuming list")
            return [s for s in lines if s.lstrip().startswith('-')]

    print("WARNING: Giving up on decoding")
    return None


def gpt_response_to_json(raw_response: Optional[str], debug=True):
    if raw_response is None:
        if debug:
            print("raw_response is None")
        return None
    wrong_input_responses = [
        "Sorry, it is not possible to create a json dict",
        "Sorry, as an AI language model",
        "The note does not mention any person" #'s name or identifier
    ]
    if any(raw_response.startswith(s) for s in wrong_input_responses):
        if debug:
            print(f"WARNING: Likely provided wrong input as GPT is complaining with {raw_response}")
        return None

    orig_response = raw_response
    # Output: ```json <text> ```
    raw_response = re.sub(r'```[a-z\s]*?(.*?) ```', r'\1', raw_response, flags=re.DOTALL)
    # For "Expecting property name enclosed in double quotes"
    # Obviously not bullet-proof for stuff like 'Ed's', can be probably
    # raw_json = raw_response.replace("'", '"')
    # GPT to rescue: Use regex to replace single quotes with double quotes
    # raw_response = re.sub(r"\'((?:[^']|(?<=\\\\)')*?[^'])\'", r'"\1"', raw_response)
    # Welp - OMG this from PPrint :facepalm:
    raw_response = raw_response.replace("{'", '{"').replace("':", '":').replace(", '", ', "')
    raw_response = raw_response.replace("',", '",').replace(": '", ': "').replace("'}", '"}')
    raw_response = raw_response.replace(': ""', ': "').replace('""}', '"}')
    # Sometimes, it includes the input in the response. So only consider what is after "Output"
    match = re.search("(?i)output:", raw_response)
    if match:
        raw_response = raw_response[match.start():]
    # Yeah, sometimes it does that lol
    #   **Output:**<br> ["Shervin: security startup guy from Maryland who wears a 1337/1338 shirt"]<br>
    raw_response = raw_response.replace('<br>\n', '\n')
    raw_response = raw_response.replace('<br />\n', '\n')
    # Sometimes GPT adds the extra comma, well, everyone is guilty of that leading to a production outage so :shrug:
    # Examples: """her so it was cool",    ],"""
    # TODO(P2, devx): Redundant character escape
    raw_response = re.sub(r'",\s*\]', '"]', raw_response)
    raw_response = re.sub(r'",\s*\}', '"}', raw_response)
    raw_response = re.sub(r'\],\s*\}', ']}', raw_response)
    raw_response = re.sub(r'\],\s*\]', ']]', raw_response)
    raw_response = re.sub(r'\},\s*\}', '}}', raw_response)
    raw_response = re.sub(r'\},\s*\]', '}]', raw_response)
    # if debug:
    #     print(f"converted {orig_response}\n\nto\n\n{raw_response}")
    try:
        # The model might have just crafted a valid json object
        result = json.loads(raw_response)
    except json.decoder.JSONDecodeError as orig_err:
        # In case there is something before the actual json output like "Output:", "Here you go:", "Sure ..".
        start_index = _get_first_occurrence(raw_response, ['{', '['])
        last_index = _get_last_occurrence(raw_response, ['}', ']'])
        raw_json = raw_response[start_index:last_index+1]  # -1 works
        if debug and len(raw_json) * 2 < len(raw_response):  # heuristic to determine that we shortened too much
            print(
                f"WARNING: likely the GPT response is NOT a JSON (shortened [{start_index}:{last_index}]):"
                f"\n{raw_json}\nresulted from\n{orig_response}"
            )
            return _try_decode_non_json(raw_response)
        try:
            result = json.loads(raw_json)
        except json.decoder.JSONDecodeError as sub_err:
            if debug:
                print(
                    f"Could NOT decode json cause SUB ERROR: {sub_err} for raw_response "
                    f"(note does a bunch of replaces) {raw_json}. ORIGINAL ERROR: {orig_err}"
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


if __name__ == "__main__":
    test_json_with_extra_output = """Output: 
    {
        "name": "Marco",
        "mnemonic": "Fashion Italy",
        "mnemonic_explanation": "Marco has an Italian name and he works in the fashion industry.",
        "industry": "Fashion",
        "role": "Unknown",
        "vibes": "Neutral",
        "priority": 2,
        "follow_ups": null,
        "needs": [
            "None mentioned."
        ]
    }"""
    result = gpt_response_to_json(test_json_with_extra_output)
    assert(result["name"] == "Marco")