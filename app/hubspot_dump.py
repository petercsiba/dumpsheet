import datetime
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Dict, List, Optional

import pytz
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
    ObjectType,
)
from common.openai_client import OpenAiClient, gpt_response_to_json
from database.account import Account
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from database.constants import DESTINATION_HUBSPOT_ID, OAUTH_DATA_TOKEN_TYPE_OAUTH
from database.models import BaseOrganization
from database.oauth_data import OauthData
from database.organization import Organization
from database.pipeline import Pipeline


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
    field_prompts = [form_field_to_gpt_prompt(field) for field in form.fields]
    return ",\n".join([f for f in field_prompts if f is not None])


def extract_form_data(
    gpt_client: OpenAiClient, form: FormDefinition, text: str
) -> Dict[str, Any]:
    # Get the current UTC time and then convert it to local time.
    local_now = datetime.datetime.now(pytz.timezone("America/Los_Angeles"))
    gpt_query = """
    Fill in the following form definition with field labels, description and type / value list:
    {form_fields}
    Based off this note:
    {note}
    Return as a valid JSON format mapping field labels to values, for unknown just use null.
    Current time is {now_with_hours_and_tz}
    """.format(
        form_fields=form_definition_to_gpt_prompt(form),
        note=text,
        # We omit minutes for 1. UX and 2. better caching of especially local test/research runs.
        # 2023-10-03 02:30 PM PDT
        now_with_hours_and_tz=local_now.strftime("%Y-%m-%d %I %p %Z"),
    )
    raw_response = gpt_client.run_prompt(gpt_query)
    form_data_raw = gpt_response_to_json(raw_response)
    if not isinstance(form_data_raw, dict):
        print(f"ERROR: gpt resulted form_data ain't a dict: {form_data_raw}")
        return form_data_raw

    form_data = {}
    for name, value in form_data_raw.items():
        field = form.get_field(name)
        if field is None:
            print(
                f"ERROR: gpt resulted field outside of the form definition: {name}: {value}, skipping"
            )
            continue

        form_data[name] = field.validate_and_fix(value)

    # TODO(P1, fullness): Would be nice to double-check if all GPT requested fields were actually returned.

    print(f"form_data={form_data}")
    return form_data


@dataclass
class HubspotDataEntry:
    transcript: str
    state: str = "new"  # "short", "incomplete", "error_gpt", "error_hubspot_sync", "warning_already_created", "success"

    contact: Optional[HubspotObject] = None
    call: Optional[HubspotObject] = None
    task: Optional[HubspotObject] = None
    contact_to_call_result: Dict[str, Any] = None
    contact_to_task_result: Dict[str, Any] = None

    gpt_contact: Optional[HubspotObject] = None
    gpt_call: Optional[HubspotObject] = None
    gpt_task: Optional[HubspotObject] = None

    def contact_name(self):
        if self.contact is not None:
            first_name = self.contact.get_value(FieldNames.FIRSTNAME.value)
            last_name = self.contact.get_value(FieldNames.LASTNAME.value)
        elif self.gpt_contact is not None:
            first_name = self.gpt_contact.get_value(FieldNames.FIRSTNAME.value)
            last_name = self.gpt_contact.get_value(FieldNames.LASTNAME.value)
        else:
            first_name = "Unknown"
            last_name = ""
        first_str = str(first_name) if bool(first_name) else ""
        last_str = str(last_name) if bool(last_name) else ""
        return f"{first_str} {last_str}"


def _count_set_fields(form_data: Dict[str, Any]) -> int:
    return sum(1 for value in form_data.values() if value is not None)


# TODO(P1, devx): REFACTOR: We should wrap this into a HubspotObject for extra validation,
#  * essentially take that code from extract_form_data and put it there.
def _maybe_add_hubspot_owner_id(form_data, hubspot_owner_id):
    if bool(form_data) and bool(hubspot_owner_id):
        try:
            int_hubspot_owner_id = int(hubspot_owner_id)
            form_data[FieldNames.HUBSPOT_OWNER_ID.value] = int_hubspot_owner_id
        except Exception:
            pass


# TODO: hubspot_owner_id might need to be int
def extract_and_sync_contact_with_follow_up(
    client: HubspotClient,
    gpt_client: OpenAiClient,
    text: str,
    hub_id: Optional[str] = None,
    hubspot_owner_id: Optional[int] = None,
    local_hack=False,
) -> HubspotDataEntry:
    # When too little text, then don't even try.
    if len(str(text)) < 50:
        print(f"WARNING: transcript too short to infer data: {text}")
        return HubspotDataEntry(
            transcript=text,
            state="short",
        )

    contact_form = FormDefinition(CONTACT_FIELDS)
    contact_data = extract_form_data(gpt_client, contact_form, text)
    _maybe_add_hubspot_owner_id(contact_data, hubspot_owner_id)
    # When it would yield too little information, rather skip and make them re-enter.
    if _count_set_fields(contact_data) <= 1:
        print(
            f"fWARNING: incomplete data entry as we could only fill in very little {contact_data} from text: {text}"
        )
        return HubspotDataEntry(
            transcript=text,
            state="incomplete",
        )

    # TODO(P1, ux): Figure out if you can create contacts without a communication channel
    if local_hack:
        # Just mock new contact for every run
        if isinstance(contact_data, dict):
            contact_data[
                FieldNames.EMAIL.value
            ] = f"example{int(time.time())}@gmail.com"
            contact_data[FieldNames.PHONE.value] = f"+1{int(time.time())}"
    contact_response = client.crm_contact_create(contact_data)
    contact_id = contact_response.hs_object_id

    call_form = FormDefinition(CALL_FIELDS)
    call_data = extract_form_data(gpt_client, call_form, text)
    _maybe_add_hubspot_owner_id(call_data, hubspot_owner_id)
    call_response = client.crm_call_create(call_data)
    call_id = call_response.hs_object_id

    # TODO(P1, ux): Sometimes, there might be no task.
    task_form = FormDefinition(TASK_FIELDS)
    task_data = extract_form_data(gpt_client, task_form, text)
    _maybe_add_hubspot_owner_id(task_data, hubspot_owner_id)
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

    if (
        contact_response.is_success()
        and call_response.is_success()
        and task_response.is_success()
    ):
        state = "success"
    else:
        if contact_data is None or call_data is None or task_data is None:
            state = "error_gpt"
        elif contact_response.status == HTTPStatus.CONFLICT:
            state = "warning_already_created"
        else:
            state = "error_hubspot_sync"

    # There are a few columns sets for the same object_type:
    # * the GPT extracted ones (call_data)
    # * the Hubspot returned (there can be a lot of metadata, even repeated values)
    # * (this) the set we want to show to our users - what was inserted into Hubspot which was generated by GPT
    # TODO(P0, devx): We should turn this into pipeline_task, prob the output should be a list of objects.
    return HubspotDataEntry(
        transcript=text,
        state=state,
        contact=HubspotObject.from_api_response_props(
            hub_id, ObjectType.CONTACT, contact_form, contact_response.get_props_if_ok()
        ),
        call=HubspotObject.from_api_response_props(
            hub_id, ObjectType.CALL, call_form, call_response.get_props_if_ok()
        ),
        task=HubspotObject.from_api_response_props(
            hub_id, ObjectType.TASK, task_form, task_response.get_props_if_ok()
        ),
        contact_to_call_result=contact_to_call_result,
        contact_to_task_result=contact_to_task_result,
        # TODO(P2, devx): This feels more like a new FormObject
        gpt_contact=HubspotObject.from_api_response_props(
            hub_id, ObjectType.CONTACT, contact_form, contact_data
        ),
        gpt_call=HubspotObject.from_api_response_props(
            hub_id, ObjectType.CALL, call_form, call_data
        ),
        gpt_task=HubspotObject.from_api_response_props(
            hub_id, ObjectType.TASK, task_form, task_data
        ),
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
        TEST_ORG_NAME = "testing locally"
        test_acc = Account.get_or_onboard_for_email(
            "petherz+localtest@gmail.com", utm_source="test"
        )

        fixture_exists = BaseOrganization.get_or_none(
            BaseOrganization.name == TEST_ORG_NAME
        )
        if bool(fixture_exists):
            organization_id = fixture_exists.id
            test_pipeline = Pipeline.get(Pipeline.organization_id == organization_id)
            print(f"reusing testing fixture for organization {organization_id}")
        else:
            test_org = Organization.get_or_create_for_account_id(
                test_acc.id, name=TEST_ORG_NAME
            )
            test_pipeline = Pipeline.get_or_create_for(
                external_org_id="external_org_id",
                organization_id=test_org.id,
                destination_id=DESTINATION_HUBSPOT_ID,
            )
            if test_pipeline.oauth_data_id is None:
                test_pipeline.oauth_data_id = OauthData.insert(
                    token_type=OAUTH_DATA_TOKEN_TYPE_OAUTH
                ).execute()
                test_pipeline.save()
        # refresh_token must come from prod, as for HubSpot oauth to work with localhost we would need have a full
        # local setup.
        OauthData.update_safely(
            oauth_data_id=test_pipeline.oauth_data_id,
            refresh_token="9ce60291-2261-48a5-8ddb-e26c9bf59845",  # TestApp - hardcoded each time
        )

        test_hs_client = HubspotClient(test_pipeline.oauth_data_id)
        # We put this into a `try` block as it's optional to go through
        owners_response = None
        try:
            owners_response = test_hs_client.list_owners()
            Account.get_or_onboard_for_hubspot(owners_response)
            org_meta = test_hs_client.get_hubspot_account_metadata()
            test_pipeline.external_org_id = str(org_meta.hub_id)
            test_pipeline.save()
            test_org.name = org_meta.hub_domain
            test_org.save()
        except Exception as e:
            print(
                f"WARNING: Cannot get or onboard owners cause {e}, response: {owners_response}"
            )

        # FOR CODE GEN
        # props = test_hs_client.list_custom_properties(object_type="contact")
        # contact_def = FormDefinition.from_properties_api_response(props.results)
        # print(f"contact_def to_python_definition: {contact_def.to_python_definition()}")
        # exit()

        test_gpt_client = OpenAiClient()

        peter_voxana_user_id = 550982168
        hs_data_entry = extract_and_sync_contact_with_follow_up(
            test_hs_client,
            test_gpt_client,
            test_data2,
            hub_id=test_pipeline.external_org_id,
            hubspot_owner_id=peter_voxana_user_id,
            local_hack=True,
        )

        from app.emails import send_hubspot_result

        send_hubspot_result(
            account_id=test_acc.id,
            idempotency_id_prefix=str(time.time()),
            data=hs_data_entry,
        )
