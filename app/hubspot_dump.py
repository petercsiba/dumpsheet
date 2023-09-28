import datetime
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from hubspot.crm.properties import Option

from app.hubspot_client import HubspotClient
from app.hubspot_models import (
    CALL_FIELDS,
    CONTACT_FIELDS,
    GPT_IGNORE_LIST,
    GPT_MAX_NUM_OPTION_FIELDS,
    TASK_FIELDS,
    AssociationType,
    FieldDefinition,
    FieldNames,
    FormDefinition,
    HubspotObject,
)
from common.openai_client import OpenAiClient, gpt_response_to_json
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from database.models import BaseAccount, BaseOnboarding, BaseOrganization
from database.organization import ORGANIZATION_ROLE_ADMIN


# Main reason to separate Definition from Values is that we can generate GPT prompts in a generic-ish way.
# Sample output "industry": "which business area they specialize in professionally",
def form_field_to_gpt_prompt(field: FieldDefinition) -> Optional[str]:
    if field.name in GPT_IGNORE_LIST:
        print(f"ignoring {field.name} for gpt prompt gen")
        return None

    result = f'"{field.name}": "{field.field_type} field representing {field.label}'

    if bool(field.description):
        result += f" described as {field.description}"
    if bool(field.options) and isinstance(field.options, list):
        if len(field.options) > GPT_MAX_NUM_OPTION_FIELDS:
            print(f"too many options, shortening to {GPT_MAX_NUM_OPTION_FIELDS}")
        options_slice: List[Option] = field.options[:GPT_MAX_NUM_OPTION_FIELDS]
        option_values = [(opt.label, opt.value) for opt in options_slice]
        result += (
            f" restricted to these options defined as a list of (label, value) {option_values}"
            " pick the most suitable value."
        )
    result += '"'

    return result


def form_definition_to_gpt_prompt(form: FormDefinition) -> str:
    field_prompts = [form_field_to_gpt_prompt(field) for field in form.fields.values()]
    return ",\n".join([f for f in field_prompts if f is not None])


def extract_form_data(
    gpt_client: OpenAiClient, form: FormDefinition, text: str
) -> Dict[str, Any]:
    gpt_query = """
    Fill in the following form definition with field labels, description and type / value list:
    {form_fields}
    Based off this note:
    {note}
    Return as a valid JSON format mapping field labels to values, for unknown just use null.
    Today is {today}
    """.format(
        form_fields=form_definition_to_gpt_prompt(form),
        note=text,
        today=datetime.date.today(),
    )
    raw_response = gpt_client.run_prompt(gpt_query)
    form_data_raw = gpt_response_to_json(raw_response)
    if not isinstance(form_data_raw, dict):
        print(f"ERROR: gpt resulted form_data ain't a dict: {form_data_raw}")
        return form_data_raw

    form_data = {}
    for name, value in form_data_raw.items():
        if name not in form.fields:
            print(
                f"ERROR: gpt resulted field outside of the form definition: {name}: {value}, skipping"
            )
            continue

        field: FieldDefinition = form.fields[name]
        form_data[name] = field.validate_and_fix(value)

    # TODO(P1, fullness): Would be nice to double-check if all GPT requested fields were actually returned.

    print(f"form_data={form_data}")
    return form_data


@dataclass
class HubspotDataEntry:
    contact: Optional[HubspotObject]
    call: Optional[HubspotObject]
    task: Optional[HubspotObject]
    contact_to_call_result: Dict[str, Any]
    contact_to_task_result: Dict[str, Any]

    gpt_contact: Optional[HubspotObject]
    gpt_call: Optional[HubspotObject]
    gpt_task: Optional[HubspotObject]

    def contact_name(self):
        first_name = self.contact.get_value(FieldNames.FIRSTNAME.value)
        last_name = self.contact.get_value(FieldNames.LASTNAME.value)
        first_str = str(first_name) if bool(first_name) else ""
        last_str = str(last_name) if bool(last_name) else ""
        return f"{first_str} {last_str}"


def extract_and_sync_contact_with_follow_up(
    client: HubspotClient, gpt_client: OpenAiClient, text: str, local_hack=False
) -> HubspotDataEntry:
    contact_form = FormDefinition(CONTACT_FIELDS)
    contact_data = extract_form_data(gpt_client, contact_form, text)
    # TODO(P1, ux): Figure out if you can create contacts without a communication channel
    if local_hack:
        # Just mock new contact for every run
        contact_data[FieldNames.EMAIL.value] = f"example{int(time.time())}@gmail.com"
        contact_data[FieldNames.PHONE.value] = f"+1{int(time.time())}"
    contact_response = client.crm_contact_create(contact_data)
    contact_id = contact_response.hs_object_id

    call_form = FormDefinition(CALL_FIELDS)
    call_data = extract_form_data(gpt_client, call_form, text)
    call_response = client.crm_call_create(call_data)
    call_id = call_response.hs_object_id

    # TODO(P1, ux): Sometimes, there might be no task.
    task_form = FormDefinition(TASK_FIELDS)
    task_data = extract_form_data(gpt_client, task_form, text)
    task_response = client.crm_task_create(task_data)
    task_id = task_response.hs_object_id

    contact_to_call_result = None
    if bool(contact_id) and bool(call_id):
        contact_to_call_result = client.crm_association_create(
            "contact", contact_id, "call", call_id, AssociationType.CONTACT_TO_CALL
        )
    contact_to_task_result = None
    if bool(contact_id) and bool(task_id):
        contact_to_task_result = client.crm_association_create(
            "contact", contact_id, "task", task_id, AssociationType.CONTACT_TO_TASK
        )
    # There are a few columns sets for the same object_type:
    # * the GPT extracted ones (call_data)
    # * the Hubspot returned (there can be a lot of metadata, even repeated values)
    # * (this) the set we want to show to our users - what was inserted into Hubspot which was generated by GPT

    return HubspotDataEntry(
        contact=HubspotObject.from_api_response_props(
            contact_form, contact_response.get_props_if_ok()
        ),
        call=HubspotObject.from_api_response_props(
            call_form, call_response.get_props_if_ok()
        ),
        task=HubspotObject.from_api_response_props(
            task_form, task_response.get_props_if_ok()
        ),
        contact_to_call_result=contact_to_call_result,
        contact_to_task_result=contact_to_task_result,
        gpt_contact=HubspotObject.from_api_response_props(contact_form, contact_data),
        gpt_call=HubspotObject.from_api_response_props(call_form, call_data),
        gpt_task=HubspotObject.from_api_response_props(task_form, task_data),
    )


test_data1 = """
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

test_data2 = """
All right, I Just got a call from Joe earner w er and er Joe His number is 714-313-3752
He is he lives in Bay Area in Fremont and And Joe is Interested in Voxana as well he wants to start using the
The product very soon. He lives in, California His Company is Supplying widgets to Tesla factory And H
e has a team of 20 Business development Representatives who are
Who are in touch with potential clients all around the u.s. He is
 He would like to understand more about how quickly we can deliver
 and what kind of pricing we're going to have he's very interesting to know if he just pays per seats
 or per number of Users Or if There's any usage pricing Also there they might be migrating to Salesforce soon.
 So he's interested to know if Even then we'll be able to support them after the migration he If this works out,
 he would be getting like 15 seats And Joe I Should he needs a little bit of time.
 They have some firefighting in it in a company going on But I should reach Back to him end of October
 right before Halloween he said And he also suggested He gave me contacts to max from Seed factory and
 Max could be potentially also interested. So I should just quickly follow up with Joe to to get us
 the introduction with max so that we can Get the ball rolling
"""

if __name__ == "__main__":
    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        fixture_exists = BaseOrganization.get_or_none(
            BaseOrganization.name == "testing locally"
        )
        if bool(fixture_exists):
            organization_id = fixture_exists.id
            print(f"reusing testing fixture for organization {organization_id}")
        else:
            # Fixtures from prod
            organization_id = BaseOrganization.insert(
                hubspot_refresh_token="9ce60291-2261-48a5-8ddb-e26c9bf59845",  # TestApp - hardcoded each time
                hubspot_linked_at=datetime.datetime.now(),
                name="testing locally",
            ).execute()
            account_id = BaseAccount.insert(
                full_name="peter csiba",
                organization_id=organization_id,
                organization_role=ORGANIZATION_ROLE_ADMIN,
            ).execute()
            BaseOnboarding.insert(
                email="petherz+localhost@gmail.com",
                account_id=account_id,
            )

        test_hs_client = HubspotClient(organization_id)

        # FOR CODE GEN
        # props = client.list_custom_properties(object_type="task")
        # contact_def = FormDefinition.from_properties_api_response(props.results)
        # print(f"contact_def gpt prompt: {contact_def.to_gpt_prompt()}")
        # print(f"contact_def to_python_definition: {contact_def.to_python_definition()}")

        test_gpt_client = OpenAiClient()

        extract_and_sync_contact_with_follow_up(
            test_hs_client, test_gpt_client, test_data2, local_hack=True
        )
