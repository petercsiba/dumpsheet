from typing import List

from app.form import FormData, FormName
from app.form_library import get_form
from common.openai_client import OpenAiClient


def run_food_ingredient_extraction(
    gpt_client: OpenAiClient, full_transcript: str
) -> List[FormData]:
    # TODO: Support multip
    food_log_form = get_form(FormName.FOOD_LOG)
    results, err = gpt_client.fill_in_multi_entry_form(
        form=food_log_form,
        task_id=None,
        text=full_transcript,
        use_current_time=True,
        print_prompt=True,
    )

    return results
