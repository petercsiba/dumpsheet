from gpt_form_filler.openai_client import OpenAiClient

from common.config import OPEN_AI_API_KEY
from common.gpt_cache import InDatabaseCacheStorage


def open_ai_client_with_db_cache(force_no_print_prompt=False) -> OpenAiClient:
    return OpenAiClient(open_ai_api_key=OPEN_AI_API_KEY, cache_store=InDatabaseCacheStorage(), force_no_print_prompt=force_no_print_prompt)
