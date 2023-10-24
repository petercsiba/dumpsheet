from typing import List

from app.form import FormDefinition, FormName
from common.openai_client import OpenAiClient

FORM_CLASSIFICATION = {
    FormName.NETWORKING: "a person i talk to at an event or virtually",
    FormName.FOOD_LOG: "an ingredient i ate",
}


def decide_on_workflow(gpt_client: OpenAiClient, text: str):
    pass


# Or maybe workflow
class Job:
    pass


# Yeah, maybe easiest is to quickly hack up the food_log stuff
# maybe one more
# and only then refactor to common pattern.
# OR, we can at least consolidate a few steps.
# Cause a lot of is quite custom, for networking there is a summary created, email logic complex
# ... so maybe FOOD_LOG can just spearhead "simple form" use cases.


def do_job(text: str, candidate_forms: List[FormDefinition]):
    pass
