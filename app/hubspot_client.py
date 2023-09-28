import datetime
import json
import re
import time
import uuid
from http import HTTPStatus
from typing import List, Optional

import pytz
from hubspot import HubSpot
from hubspot.auth import oauth
from hubspot.crm import contacts
from hubspot.crm.contacts import SimplePublicObjectInputForCreate
from hubspot.crm.objects import AssociationSpec, calls, tasks
from hubspot.crm.properties import Option

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
)
from common.config import HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET, HUBSPOT_REDIRECT_URL
from common.openai_client import OpenAiClient, gpt_response_to_json
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from database.models import BaseAccount, BaseOnboarding, BaseOrganization
from database.organization import ORGANIZATION_ROLE_ADMIN


class ApiSingleResponse:
    def __init__(self, status, data, hs_object_id=None):
        self.status = status
        # Set options fields
        self.hs_object_id = hs_object_id
        self.properties = None
        self.error = None

        if 200 <= self.status < 300:
            # asserting it is SimplePublicObject
            self.properties = data.properties
            if bool(self.properties):
                self.hs_object_id = self.properties.get(FieldNames.HS_OBJECT_ID)
            if self.hs_object_id is None:
                self.hs_object_id = data.id
        else:
            self.error = data

        # `data` has more, like ['archived', 'archived_at', 'created_at', 'properties_with_history', ...]
        # but we ignore it for now


class HubspotClient:
    def __init__(self, organization_id: uuid.UUID):
        self.api_client = HubSpot()
        self.expires_at_cache = None
        self.organization_id = organization_id
        self._ensure_token_fresh()

    # TODO(P0, bug): We have to somehow use the refresh token to get new access_tokens
    # https://legacydocs.hubspot.com/docs/methods/oauth2/oauth2-quickstart#refreshing-oauth-20-tokens
    def _ensure_token_fresh(self):
        if self.expires_at_cache is None:
            organization = BaseOrganization.get_by_id(self.organization_id)
            self.expires_at_cache = organization.hubspot_expires_at
            if bool(self.expires_at_cache):
                self.api_client.access_token = organization.hubspot_access_token
                print(
                    f"reusing cached access token valid until {self.expires_at_cache}"
                )

        # TODO(P1, effectivity): The TZ comparison seems to be not working.
        if self.expires_at_cache is None or self.expires_at_cache.astimezone(
            pytz.UTC
        ) < datetime.datetime.now(pytz.UTC):
            print(f"gonna refresh token for organization {self.organization_id}")
            try:
                organization = BaseOrganization.get_by_id(self.organization_id)

                # We assume the Auth was already granted, and that the Organization already has a refresh_token there.
                tokens = self.api_client.auth.oauth.tokens_api.create(
                    grant_type="refresh_token",
                    client_id=HUBSPOT_CLIENT_ID,
                    client_secret=HUBSPOT_CLIENT_SECRET,
                    redirect_uri=HUBSPOT_REDIRECT_URL,
                    refresh_token=organization.hubspot_refresh_token,
                )
                organization.hubspot_access_token = tokens.access_token
                organization.hubspot_refresh_token = tokens.refresh_token
                # We subtract 60 seconds to make more real.
                organization.hubspot_expires_at = (
                    datetime.datetime.now()
                    + datetime.timedelta(seconds=tokens.expires_in - 60)
                )
                organization.save()

                self.expires_at_cache = organization.hubspot_expires_at
                self.api_client.access_token = organization.hubspot_access_token
                print(f"token refreshed, expires at {self.expires_at_cache}")
            except oauth.ApiException as e:
                print(f"Exception when fetching access token: {e}")

    def _handle_exception(
        self, endpoint: str, e: contacts.ApiException, request_body=None
    ) -> ApiSingleResponse:
        body = json.loads(e.body)
        msg = body.get("message", str(e))
        req = (
            f"request_body: {str(request_body)}"
            if bool(request_body)
            else "no request body"
        )
        hs_object_id = None
        if e.status == HTTPStatus.CONFLICT:
            match = re.search(r"Existing ID:\s*(\d+)", msg)
            if match:
                hs_object_id = int(match.group(1))
            # TODO(P1, reliability): Refetch object and return it

        print(
            f"ERROR Hubspot API call HTTP {e.status} for {endpoint} with {req}: {msg}"
        )
        return ApiSingleResponse(
            e.status, body.get("message", str(e)), hs_object_id=hs_object_id
        )

    def crm_contact_create(self, props) -> ApiSingleResponse:
        self._ensure_token_fresh()
        request_body = SimplePublicObjectInputForCreate(properties=props)
        try:
            api_response = self.api_client.crm.contacts.basic_api.create(
                simple_public_object_input_for_create=request_body
            )
            print(f"Contact created ({type(api_response)}): {api_response}")
            return ApiSingleResponse(HTTPStatus.OK, api_response)
        except contacts.ApiException as e:
            return self._handle_exception("contact create", e, request_body)

    def crm_contact_get_all(self):
        self._ensure_token_fresh()
        try:
            # Handles the pagination with default limit = 100
            return self.api_client.crm.contacts.get_all()
        except contacts.ApiException as e:
            return self._handle_exception("contact get_all", e)

    def crm_call_create(self, props) -> ApiSingleResponse:
        self._ensure_token_fresh()
        request_body = SimplePublicObjectInputForCreate(
            properties=props,
        )
        try:
            api_response = self.api_client.crm.objects.calls.basic_api.create(
                simple_public_object_input_for_create=request_body
            )
            print(f"Call created: {api_response}")
            return ApiSingleResponse(HTTPStatus.OK, api_response)
        except calls.ApiException as e:
            return self._handle_exception("call create", e, request_body)

    def crm_task_create(self, props) -> ApiSingleResponse:
        self._ensure_token_fresh()
        request_body = SimplePublicObjectInputForCreate(
            properties=props,
        )
        try:
            api_response = self.api_client.crm.objects.tasks.basic_api.create(
                simple_public_object_input_for_create=request_body
            )
            print(f"Task created: {api_response}")
            return ApiSingleResponse(HTTPStatus.OK, api_response)
        except tasks.ApiException as e:
            return self._handle_exception("create task", e, request_body)

    # https://community.hubspot.com/t5/APIs-Integrations/Creating-associations-in-hubspot-api-nodejs-new-version/td-p/803292
    # TODO(P1, devx): We can derive from_type and to_type from assoc_type
    def crm_association_create(
        self,
        from_type: str,
        from_id: int,
        to_type: str,
        to_id: int,
        assoc_type: AssociationType,
    ):
        # TODO(P1, reliability): Handle error without code failing
        self._ensure_token_fresh()
        api_response = self.api_client.crm.associations.v4.basic_api.create(
            object_type=from_type,
            object_id=from_id,
            to_object_type=to_type,
            to_object_id=to_id,
            association_spec=[
                AssociationSpec(
                    # ["HUBSPOT_DEFINED", "USER_DEFINED", "INTEGRATOR_DEFINED"]
                    association_category="HUBSPOT_DEFINED",
                    association_type_id=assoc_type.value,
                )
            ],
        )
        print(f"Association created: {api_response}")
        # Example: {from_object_type_id '0-1', to_object_type_id: '0-27' ... }
        return api_response

    def list_custom_properties(self, object_type="contact"):
        properties_api = self.api_client.crm.properties.core_api
        try:
            response = properties_api.get_all(object_type=object_type)
            # print(f"structure of list_custom_properties ({type(response).__name__}): {dir(response)}")
            return response
        except Exception as e:
            print(f"Exception when listing custom properties: {e}")
            return None


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


def extract_form_data(gpt_client: OpenAiClient, form: FormDefinition, text: str):
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

        client = HubspotClient(organization_id)

        # FOR CODE GEN
        # props = client.list_custom_properties(object_type="task")
        # contact_def = FormDefinition.from_properties_api_response(props.results)
        # print(f"contact_def gpt prompt: {contact_def.to_gpt_prompt()}")
        # print(f"contact_def to_python_definition: {contact_def.to_python_definition()}")

        gpt_client = OpenAiClient()
        contact_form = FormDefinition(CONTACT_FIELDS)
        contact_data = extract_form_data(gpt_client, contact_form, test_data)
        # Just mock new contact for every run
        contact_data[FieldNames.EMAIL.value] = f"example{int(time.time())}@gmail.com"
        contact_data[FieldNames.PHONE.value] = f"+1{int(time.time())}"
        contact_response = client.crm_contact_create(contact_data)
        contact_id = contact_response.hs_object_id

        call_form = FormDefinition(CALL_FIELDS)
        call_data = extract_form_data(gpt_client, call_form, test_data)
        call_response = client.crm_call_create(call_data)
        call_id = call_response.hs_object_id

        task_form = FormDefinition(TASK_FIELDS)
        task_data = extract_form_data(gpt_client, task_form, test_data)
        task_response = client.crm_task_create(task_data)
        task_id = task_response.hs_object_id

        client.crm_association_create(
            "contact", contact_id, "call", call_id, AssociationType.CONTACT_TO_CALL
        )
        client.crm_association_create(
            "contact", contact_id, "task", task_id, AssociationType.CONTACT_TO_TASK
        )
