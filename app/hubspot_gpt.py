from app.hubspot_models import CONTACT_FIELDS, FormDefinition
from common.openai_client import OpenAiClient, gpt_response_to_json
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres


def extract_form_data(gpt_client: OpenAiClient, form: FormDefinition, text: str):
    gpt_query = """
    Fill in the following form definition with field labels, description and type / value list:
    {form_fields}
    Based off this note:
    {note}
    Return as a valid JSON format mapping field labels to values, for unknown just use null.
    """.format(
        form_fields=form.to_gpt_prompt(), note=text
    )
    raw_response = gpt_client.run_prompt(gpt_query)
    form_data = gpt_response_to_json(raw_response)
    print(f"form_data={form_data}")


test_data = """
Okay, I just talked to Jen Jennifer Ma Jen is interested in our product
Jen's phone number is 703-887-5647 She called me today,
and she would like to get her Tax or business development team in her
So she's in tax Tax services tax department,
and she would like to get her biz dev team on the Voxana She's got Three account executives
Who are taking care of like the existing sorry not like three junior ones and then another
One two three four senior ones she has seven account executives,
and then she has this like lead called lead reach out people
which are another two like more junior people who are
Like called calling and called reaching out on LinkedIn So she has a
Altogether team of nine She they're all based in San Francisco,
California and On her email is Jennifer double n Jennifer dot ma at Griffith
tax Dot-com Griffith is spelled G R Y F F I T tax dot-com Mmm And
she asked me She asked me to schedule a demo This week is too busy for her
So we should schedule the demo sometime next week
And it's it's my my action to come up with a good proposals when to do it next wee
"""


if __name__ == "__main__":
    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        gpt_client = OpenAiClient()
        form = FormDefinition(CONTACT_FIELDS)
        extract_form_data(gpt_client, form, test_data)
