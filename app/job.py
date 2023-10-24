# Intent of this class is to act as a control / template for the most common use-case we have at Voxana, kinda like ETL:
# * Uploads voice
# * Transcribes
# * Picks workflow (e.g. networking_dump, hubspot_sync, just voice-note)
# * * (Optional) Does pre-processing, e.g. split the transcript into multiple chunks / items.
# *
# *
# *
from typing import List

from app.form import FormDefinition, FormName

FORM_CLASSIFICATION = {
    FormName.NETWORKING: "a person i talk to at an event or virtually",
    FormName.FOOD_LOG: "an ingredient i ate",
}


def do_job(text: str, candidate_forms: List[FormDefinition]):
    pass
