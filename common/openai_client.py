# TODO(P0, devx, quality): Update chat-gpt model usage, ideally use those functions too!
#  * https://platform.openai.com/docs/guides/gpt/function-calling
#   Define a function called
#       extract_people_data(people: [
#           {name: string, birthday: string, location: string}
#       ]), to extract all people mentioned in a Wikipedia article.
# TODO(P1, devx): This Haystack library looks quite good https://github.com/deepset-ai/haystack
# TODO(P3, research, fine-tune): TLDR; NOT worth it. Feels like for repeated tasks it would be great to
#  speed up and/or cost save https://platform.openai.com/docs/guides/fine-tuning/advanced-usage
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import List, Optional

import openai
import tiktoken
from peewee import InterfaceError

from common.aws_utils import is_running_in_aws
from common.config import OPEN_AI_API_KEY
from common.storage_utils import get_fileinfo
from common.utils import Timer
from database.models import BasePromptLog

# TODO(P1, specify organization id): Header OpenAI-Organization
openai.api_key = OPEN_AI_API_KEY
# https://platform.openai.com/docs/models/gpt-4
DEFAULT_MODEL = "gpt-4-0613"  # Thanks Vishal
# Sometimes seems the newest models experience downtime-so try to backup.
BACKUP_MODEL = "gpt-3.5-turbo"
BACKUP_MODEL_AFTER_NUM_RETRIES = 3
# DEFAULT_MODEL = "gpt-3.5-turbo-0613"


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


# NOTE: This somewhat evolved from text-based GPT prompts to also include other API calls
class PromptLog(BasePromptLog):
    class Meta:
        # db_table = BasePromptLog.Meta.table_name
        # TODO(p1, devx): Figure out why peewee uses "promptlog" for queries, heard they try derive it from class name?
        #   GPT claims "db_table" has no effect - but it actually fixes stuff.
        db_table = "prompt_log"

    def total_tokens(self) -> int:
        if self.prompt_tokens is None or self.completion_tokens is None:
            return 0
        return self.prompt_tokens + self.completion_tokens

    @staticmethod
    def get_prompt_hash(prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    @staticmethod
    def get_or_create_from_cache(prompt, model):
        prompt_hash = PromptLog.get_prompt_hash(prompt)
        try:
            return PromptLog.get(
                PromptLog.prompt_hash == prompt_hash, PromptLog.model == model
            )
        except PromptLog.DoesNotExist:
            return PromptLog(
                prompt=prompt, prompt_hash=prompt_hash, model=model, result=None
            )
        except InterfaceError:
            print("DB NOT connected, NOT using gpt prompt caching")
            return PromptLog(prompt=prompt, prompt_hash=prompt_hash, model=model)

    def write_cache(self) -> List:
        try:
            res = self.save()
            print(f"prompt_log: written to cache {self.model}:{self.prompt_hash}")
            return res
        except InterfaceError:
            print("DB NOT connected, NOT using gpt prompt caching")
            return []


class PromptCache:
    def __init__(self, cache_key: str, model: str, print_prompt: bool):
        self.cache_key = cache_key
        self.model = model
        self.print_prompt: bool = print_prompt
        self.prompt_log: Optional[PromptLog] = None
        self.cache_hit: bool = False
        self.start_time: Optional[float] = None

    def __enter__(self):
        if self.print_prompt:
            loggable_prompt = self.cache_key.replace("\n", " ")
            print(f"Asking {self.model} for: {loggable_prompt}")

        self.prompt_log = PromptLog.get_or_create_from_cache(self.cache_key, self.model)
        if bool(self.prompt_log.result):
            self.cache_hit = True
            print(
                f"prompt_log: serving from cache {self.model}:{self.prompt_log.prompt_hash}"
            )
            if self.prompt_log.prompt != self.cache_key:
                print(
                    f"ERROR: hash collision for {self.prompt_log.prompt_hash} for prompt {self.cache_key}"
                )

        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.prompt_log.request_time_ms = int(1000 * (time.time() - self.start_time))
        if self.print_prompt:
            print(
                f"{self.model}: { self.prompt_log.request_time_ms / 1000} seconds used {self.prompt_log.total_tokens()}"
            )

        if self.prompt_log.result is not None and not self.cache_hit:
            self.prompt_log.write_cache()


class OpenAiClient:
    def __init__(self):
        print("OpenAiClient init")
        # In-memory representation of the above to mostly sum up stats.
        self.force_no_print_prompt = False
        self.prompt_stats: List[PromptLog] = []

    def _should_print_prompt(self, print_prompt_arg: bool):
        if self.force_no_print_prompt:
            return False
        return print_prompt_arg

    def sum_up_prompt_stats(self) -> PromptStats:
        stats = PromptStats()
        for prompt_log in self.prompt_stats:
            stats.prompt_tokens += prompt_log.prompt_tokens
            stats.completion_tokens += prompt_log.completion_tokens
            stats.request_time_ms += prompt_log.request_time_ms

        stats.total_requests = len(self.prompt_stats)
        stats.total_tokens = stats.prompt_tokens + stats.completion_tokens
        return stats

    def _run_prompt(
        self, prompt: str, model=DEFAULT_MODEL, retry_timeout=10, retry_num=0
    ):
        # wait is too long so carry on
        if retry_timeout > 300:
            print("ERROR: waiting for prompt too long")
            return None
        if retry_num >= BACKUP_MODEL_AFTER_NUM_RETRIES and model != BACKUP_MODEL:
            print(
                f"WARNING: Changing model from {model} to {BACKUP_MODEL} after {retry_num} retries"
            )
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
        except (
            openai.error.RateLimitError,
            openai.error.Timeout,
            openai.error.TryAgain,
        ) as err:
            print(
                f"Got time-based {type(err)} error - sleeping for {retry_timeout} cause {err}"
            )
            should_retry = True
            time.sleep(retry_timeout)
        # Their fault
        except (openai.error.APIError, openai.error.ServiceUnavailableError) as err:
            print(
                f"Got server-side {type(err)} error - sleeping for {retry_timeout} cause {err}"
            )
            should_retry = True
            time.sleep(retry_timeout)
        # Our fault
        except (
            openai.error.InvalidRequestError,
            openai.error.InvalidAPIType,
            openai.error.AuthenticationError,
        ) as err:
            print(
                f"Got client-side {type(err)} error - we messed up so lets rethrow this error {err}"
            )
            raise err

        if should_retry:
            return self._run_prompt(
                prompt, model, 2 * retry_timeout, retry_num=retry_num + 1
            )  # exponential backoff

        return response

    # About 0.4 cents per request (about 2000 tokens). Using gpt-4 would be 15x more expensive :/
    # TODO(peter): Do sth about max prompt length (4096 tokens INCLUDING the generated response)
    # TODO(P1, devx): We should templatize the prompt into "function body" and "parameters";
    #   then we can re-use the "body" to "fine-tune" a model and have faster responses.
    def run_prompt(self, prompt: str, model=DEFAULT_MODEL, print_prompt=True):
        with PromptCache(
            cache_key=prompt,
            model=model,
            print_prompt=self._should_print_prompt(print_prompt),
        ) as pcm:
            if pcm.cache_hit:
                return pcm.prompt_log.result

            response = self._run_prompt(prompt, model)
            if response is None:
                return None

            gpt_result = response.choices[0].message.content.strip()
            token_usage = response["usage"]
            pcm.prompt_log.result = gpt_result
            pcm.prompt_log.prompt_tokens = token_usage.get("prompt_tokens", 0)
            pcm.prompt_log.completion_tokens = token_usage.get("completion_tokens", 0)
            self.prompt_stats.append(pcm.prompt_log)
            # `pcm.__exit__` will update the database

            return gpt_result

    # They claim to return 1536 dimension of normalized to 1 (cosine or euclid returns same)
    # TODO(P1, research): There are a LOT of unknowns here for me:
    #   * How it works with larger texts?
    #   * What is LangChan good for? It feels just like a layer on top of (OpenAI) models.
    def get_embedding(self, text, model="text-embedding-ada-002"):
        text = text.replace("\n", " ")
        print(
            f"Running embedding for {num_tokens_from_string(text)} token of text {text[:100]}"
        )
        with Timer("Embedding"):
            embedding = openai.Embedding.create(input=[text], model=model)["data"][0][
                "embedding"
            ]
            # print(f"Embedding: {embedding}")
            return embedding

    # TODO(P2, Facebook MMS): Better multi-language support, Slovak was OK, but it got some things quite wrong.
    #   * https://about.fb.com/news/2023/05/ai-massively-multilingual-speech-technology/
    #   We might need to run the above ourselves for now (BaseTen hosting?)
    #   For inspiration on how to run Whisper locally:
    #   https://towardsdatascience.com/whisper-transcribe-translate-audio-files-with-human-level-performance-df044499877
    # They claim to have WER <50% for these:
    # Afrikaans, Arabic, Armenian, Azerbaijani, Belarusian, Bosnian, Bulgarian, Catalan, Chinese, Croatian, Czech,
    # Danish, Dutch, English, Estonian, Finnish, French, Galician, German, Greek, Hebrew, Hindi, Hungarian, Icelandic,
    # Indonesian, Italian, Japanese, Kannada, Kazakh, Korean, Latvian, Lithuanian, Macedonian, Malay, Marathi, Maori,
    # Nepali, Norwegian, Persian, Polish, Portuguese, Romanian, Russian, Serbian, Slovak, Slovenian, Spanish, Swahili,
    # Swedish, Tagalog, Tamil, Thai, Turkish, Ukrainian, Urdu, Vietnamese, and Welsh.
    # NOTE: I verified that for English there is no difference between "transcribe" and "translate",
    # by changing it locally and seeing the translate is "cached_prompt: serving out of cache".
    def transcribe_audio(self, audio_filepath, model="whisper-1"):
        prompt_hint = "notes on my discussion from an in-person meeting or conference"

        # We mainly do caching
        with PromptCache(
            cache_key=audio_filepath,
            model=model,
            print_prompt=self._should_print_prompt(True),
        ) as pcm:
            # We only use the cache for local runs to further speed up development (and reduce cost)
            if pcm.cache_hit and not is_running_in_aws():
                return pcm.prompt_log.result

            with open(audio_filepath, "rb") as audio_file:
                # TODO(P0, bug): Seems like empty audio files can get stuck here (maybe temperature=0 and backoff?).
                print(
                    f"Transcribing (and translating) {get_fileinfo(file_handle=audio_file)}"
                )
                # Data submitted through the API is no longer used for service improvements (including model training)
                #   unless the organization opts in
                # https://openai.com/blog/introducing-chatgpt-and-whisper-apis
                # (2023, May): File uploads are currently limited to 25 MB and the these file types are supported:
                #   mp3, mp4, mpeg, mpga, m4a, wav, and webm (m4a FAKE news). Confirmed that webm and ffmpeg mp4 work.
                # TODO(P2, feature); For longer inputs, we can use pydub to chunk it up
                #   https://platform.openai.com/docs/guides/speech-to-text/longer-inputs
                res = openai.Audio.translate(
                    model=model,
                    file=audio_file,
                    response_format="json",
                    # language="en",  # only for openai.Audio.transcribe
                    prompt=prompt_hint,
                    # If set to 0, the model will use log probability to automatically increase the temperature
                    #   until certain thresholds are hit (i.e. it can take longer).
                    temperatue=0,
                )
                transcript = res["text"]
                print(f"audio transcript: {res}")
                pcm.prompt_log.result = transcript
                # `pcm.__exit__` will update the database
                return transcript


def _get_first_occurrence(s: str, list_of_chars: list):
    first_occurrence = len(s)  # initialize to length of the string

    for char in list_of_chars:
        index = s.find(char)
        if (
            index != -1 and index < first_occurrence
        ):  # update if char found and it's earlier
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
        bullet_point_lines = sum(s.lstrip().startswith("-") for s in lines)
        if bullet_point_lines + 1 >= len(lines):
            print(
                f"Most of lines {bullet_point_lines} out of {len(lines)} start as a bullet point, assuming list"
            )
            return [s for s in lines if s.lstrip().startswith("-")]

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
        "The note does not mention any person",  # 's name or identifier
    ]
    if any(raw_response.startswith(s) for s in wrong_input_responses):
        if debug:
            print(
                f"WARNING: Likely provided wrong input as GPT is complaining with {raw_response}"
            )
        return None

    orig_response = raw_response
    # Output: ```json <text> ```
    raw_response = re.sub(
        r"```[a-z\s]*?(.*?) ```", r"\1", raw_response, flags=re.DOTALL
    )
    # For "Expecting property name enclosed in double quotes"
    # Obviously not bullet-proof for stuff like 'Ed's', can be probably
    # raw_json = raw_response.replace("'", '"')
    # GPT to rescue: Use regex to replace single quotes with double quotes
    # raw_response = re.sub(r"\'((?:[^']|(?<=\\\\)')*?[^'])\'", r'"\1"', raw_response)
    # Welp - OMG this from PPrint :facepalm:
    raw_response = (
        raw_response.replace("{'", '{"').replace("':", '":').replace(", '", ', "')
    )
    raw_response = (
        raw_response.replace("',", '",').replace(": '", ': "').replace("'}", '"}')
    )
    raw_response = raw_response.replace(': ""', ': "').replace('""}', '"}')
    # Sometimes, it includes the input in the response. So only consider what is after "Output"
    match = re.search("(?i)output:", raw_response)
    if match:
        raw_response = raw_response[match.start() :]
    # Yeah, sometimes it does that lol
    #   **Output:**<br> ["Shervin: security startup guy from Maryland who wears a 1337/1338 shirt"]<br>
    raw_response = raw_response.replace("<br>\n", "\n")
    raw_response = raw_response.replace("<br />\n", "\n")
    # Sometimes GPT adds the extra comma, well, everyone is guilty of that leading to a production outage so :shrug:
    # Examples: """her so it was cool",    ],"""
    # TODO(P2, devx): Redundant character escape
    raw_response = re.sub(r'",\s*\]', '"]', raw_response)
    raw_response = re.sub(r'",\s*\}', '"}', raw_response)
    raw_response = re.sub(r"\],\s*\}", "]}", raw_response)
    raw_response = re.sub(r"\],\s*\]", "]]", raw_response)
    raw_response = re.sub(r"\},\s*\}", "}}", raw_response)
    raw_response = re.sub(r"\},\s*\]", "}]", raw_response)
    # if debug:
    #     print(f"converted {orig_response}\n\nto\n\n{raw_response}")
    try:
        # The model might have just crafted a valid json object
        res = json.loads(raw_response)
    except json.decoder.JSONDecodeError as orig_err:
        # In case there is something before the actual json output like "Output:", "Here you go:", "Sure ..".
        start_index = _get_first_occurrence(raw_response, ["{", "["])
        last_index = _get_last_occurrence(raw_response, ["}", "]"])
        raw_json = raw_response[start_index : last_index + 1]  # -1 works
        if debug and len(raw_json) * 2 < len(
            raw_response
        ):  # heuristic to determine that we shortened too much
            print(
                f"WARNING: likely the GPT response is NOT a JSON (shortened [{start_index}:{last_index}]):"
                f"\n{raw_json}\nresulted from\n{orig_response}"
            )
            return _try_decode_non_json(raw_response)
        try:
            res = json.loads(raw_json)
        except json.decoder.JSONDecodeError as sub_err:
            if debug:
                print(
                    f"Could NOT decode json cause SUB ERROR: {sub_err} for raw_response "
                    f"(note does a bunch of replaces) {raw_json}. ORIGINAL ERROR: {orig_err}"
                )
            return None
    return res


def gpt_response_to_json_list(raw_response) -> List:
    response = gpt_response_to_json(raw_response)
    # Solves TypeError: unhashable type: 'slice'
    if isinstance(response, dict):
        print(
            f"WARNING: expected response to be a list, got a dict for {str(response)[:100]}. Only using values."
        )
        return [f"{value}" for key, value in response.items()]
    elif isinstance(response, list):
        # Sometimes it's a list of dicts, so convert each person object to just a plain string.
        return [gpt_response_to_plaintext(str(person)) for person in response]

    print(f"ERROR response got un-expected type {type(response)}: {response}")
    return []


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
    except Exception as e:
        print(f"WARNING: gpt_response_to_plaintext encountered an error {e}")
        pass

    return str(raw_response)


# TODO(P1, test): I used to have a set of weird GPT "json"-like responses, we should add tests for them.
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
    res = gpt_response_to_json(test_json_with_extra_output)
    assert res["name"] == "Marco"
