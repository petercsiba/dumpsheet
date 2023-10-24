import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Dict, List, Optional

from hubspot.crm.properties import ModelProperty

from app.form import FormData, FormDefinition, FormName
from app.form_library import get_form
from app.hubspot_client import HubspotClient
from app.hubspot_models import (
    ALLOWED_FIELDS,
    AssociationType,
    FieldDefinition,
    FieldNames,
    HubspotObject,
    ObjectType,
)
from common.openai_client import OpenAiClient
from database.account import Account
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from database.constants import DESTINATION_HUBSPOT_ID, OAUTH_DATA_TOKEN_TYPE_OAUTH
from database.email_log import EmailLog
from database.models import BaseDataEntry, BaseOrganization
from database.oauth_data import OauthData
from database.organization import Organization
from database.pipeline import Pipeline
from database.task import KEY_HUBSPOT_CALL, KEY_HUBSPOT_CONTACT, KEY_HUBSPOT_TASK, Task


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
            first_name = self.contact.get_display_value(FieldNames.FIRSTNAME.value)
            last_name = self.contact.get_display_value(FieldNames.LASTNAME.value)
        elif self.gpt_contact is not None:
            first_name = self.gpt_contact.get_display_value(FieldNames.FIRSTNAME.value)
            last_name = self.gpt_contact.get_display_value(FieldNames.LASTNAME.value)
        else:
            first_name = "Unknown"
            last_name = ""
        first_str = str(first_name) if bool(first_name) else ""
        last_str = str(last_name) if bool(last_name) else ""
        return f"{first_str} {last_str}"


def _count_set_fields(form_data: FormData) -> int:
    return sum(1 for value in form_data.to_dict() if value is not None)


# TODO(P1, devx): REFACTOR: We should wrap this into a HubspotObject for extra validation,
#  * essentially take that code from extract_form_data and put it there.
def _maybe_add_hubspot_owner_id(form_data: FormData, hubspot_owner_id):
    if bool(form_data) and bool(hubspot_owner_id):
        int_hubspot_owner_id = None
        try:
            int_hubspot_owner_id = int(hubspot_owner_id)
            form_data.set_field_value(
                FieldNames.HUBSPOT_OWNER_ID.value, int_hubspot_owner_id
            )
        except Exception as ex:
            print(
                f"WARNING: Cannot set hubspot_owner_id {int_hubspot_owner_id} cause {ex}"
            )
            pass


# TODO: hubspot_owner_id might need to be int
def extract_and_sync_contact_with_follow_up(
    client: HubspotClient,
    gpt_client: OpenAiClient,
    db_task: Task,
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

    # CONTACT CREATION
    contact_form = get_form(FormName.HUBSPOT_CONTACT)
    contact_form_data, contact_err = gpt_client.fill_in_form(
        form=contact_form, task_id=db_task.id, text=text
    )
    _maybe_add_hubspot_owner_id(contact_form_data, hubspot_owner_id)
    db_task.add_generated_output(KEY_HUBSPOT_CONTACT, contact_form_data)

    # When it would yield too little information, rather skip and make them re-enter.
    if _count_set_fields(contact_form_data) <= 1:
        print(
            f"fWARNING: incomplete data entry as too little fields filled for {contact_form_data} from text: {text}"
        )
        return HubspotDataEntry(
            transcript=text,
            state="incomplete",
        )

    # TODO(P1, ux): Figure out if you can create contacts without a communication channel
    if local_hack:
        # Just mock new contact for every run
        if bool(contact_form_data):
            contact_form_data.set_field_value(
                FieldNames.EMAIL.value, f"example{int(time.time())}@gmail.com"
            )
            contact_form_data.set_field_value(
                FieldNames.PHONE.value, f"+1650210{int(time.time()) % 10000}"
            )

    contact_response = client.crm_contact_create(contact_form_data.to_dict())
    db_task.add_sync_response(
        KEY_HUBSPOT_CONTACT,
        contact_response.status,
        contact_response.get_task_response(),
    )
    contact_id = contact_response.hs_object_id

    # CALL CREATION
    call_form = get_form(FormName.HUBSPOT_MEETING)
    # use_current_time so hs_timestamp gets filled
    call_form_data, call_err = gpt_client.fill_in_form(
        form=call_form, task_id=db_task.id, text=text, use_current_time=True
    )
    _maybe_add_hubspot_owner_id(call_form_data, hubspot_owner_id)
    db_task.add_generated_output(KEY_HUBSPOT_CALL, call_form_data)

    call_response = client.crm_call_create(call_form_data.to_dict())
    db_task.add_sync_response(
        KEY_HUBSPOT_CALL, call_response.status, call_response.get_task_response()
    )
    call_id = call_response.hs_object_id

    # TASK CREATION
    # TODO(P1, ux): Sometimes, there might be no task.
    hs_task_form = get_form(FormName.HUBSPOT_TASK)
    # use_current_time so hs_timestamp gets filled
    hs_task_data, hs_task_err = gpt_client.fill_in_form(
        form=hs_task_form, task_id=db_task.id, text=text, use_current_time=True
    )
    _maybe_add_hubspot_owner_id(hs_task_data, hubspot_owner_id)
    db_task.add_generated_output(KEY_HUBSPOT_TASK, hs_task_data)

    hs_task_response = client.crm_task_create(hs_task_data.to_dict())
    db_task.add_sync_response(
        KEY_HUBSPOT_TASK, hs_task_response.status, hs_task_response.get_task_response()
    )
    hs_task_id = hs_task_response.hs_object_id

    # ASSOCIATION CREATION
    contact_to_call_result = None
    if bool(contact_id) and bool(call_id):
        contact_to_call_result = client.crm_association_create(
            "contact", contact_id, "call", call_id, AssociationType.CONTACT_TO_CALL
        )
    contact_to_task_result = None
    if bool(contact_id) and bool(hs_task_id):
        contact_to_task_result = client.crm_association_create(
            "contact", contact_id, "task", hs_task_id, AssociationType.CONTACT_TO_TASK
        )

    if (
        contact_response.is_success()
        and call_response.is_success()
        and hs_task_response.is_success()
    ):
        state = "success"
    else:
        if contact_form_data is None or call_form_data is None or hs_task_data is None:
            state = "error_gpt"
        elif contact_response.status == HTTPStatus.CONFLICT:
            state = "warning_already_created"
        else:
            state = "error_hubspot_sync"

    db_task.finish()

    # There are a few columns sets for the same object_type:
    # * the GPT extracted ones (call_data)
    # * the Hubspot returned (there can be a lot of metadata, even repeated values)
    # * (this) the set we want to show to our users - what was inserted into Hubspot which was generated by GPT
    # Admittedly, this is quite messy. After hacking it together quickly, I wanted to have a first pass on a more
    # general "fill any form" use-case.
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
            hub_id, ObjectType.TASK, hs_task_form, hs_task_response.get_props_if_ok()
        ),
        contact_to_call_result=contact_to_call_result,
        contact_to_task_result=contact_to_task_result,
        # TODO(P2, devx): This feels more like a new FormObject
        gpt_contact=HubspotObject.from_api_response_props(
            hub_id, ObjectType.CONTACT, contact_form, contact_form_data.to_dict()
        ),
        gpt_call=HubspotObject.from_api_response_props(
            hub_id, ObjectType.CALL, call_form, call_form_data.to_dict()
        ),
        gpt_task=HubspotObject.from_api_response_props(
            hub_id, ObjectType.TASK, hs_task_form, hs_task_data.to_dict()
        ),
    )


def _gen_field_from_properties_api_response(response: ModelProperty) -> FieldDefinition:
    return FieldDefinition(
        name=response.name,
        field_type=response.field_type,
        label=response.label,
        description=response.description,
        options=response.options,
        custom_field=response.hubspot_defined
        is False,  # only if non-none and set to False it is a custom field
    )


def _gen_form_from_properties_api_response(
    form_name: FormName,
    field_list: List[ModelProperty],
) -> FormDefinition:
    fields = []
    for field_response in [f for f in field_list if f.name in ALLOWED_FIELDS]:
        field: FieldDefinition = _gen_field_from_properties_api_response(field_response)
        fields.append(field)
    return FormDefinition(form_name, fields)


test_data1 = """
okay, then I spoke with Andrey Yursa he is from Zhilina which is funny he went to the private high school
the english one in Zhilina and then he went to Suchany for the rest of his high school he played a
lot of ice hockey which is funny with my cousin Alex Andrey is super outgoing and and yeah so he
 studied philosophy at King's College and he says that he was very religious and that's why he was interested in
 that and he was like involved with the evangelical church but he lost his religiousness and now he went into
 business he said he worked during his college in the UK he worked for leave part-time like for two years and
 he was reaching out to Slovak professionals living abroad and connecting them to the Slovak community that's
 how he remembers he got in touch with Peter my co-founder so and during his second year at college he while
 he was working for leave he got introduced to Marek and Marek was very impressed by Andrey's like outgoingness
 and his like fearlessness how he's approaching people so yeah Andrey seems to be like a straight shooter he
 did study for one year in the US during his high school and he played hockey in Vermont and recalls that he
  like he was the captain of the team and when the when the coach was shouting at him for being just too rude
  he felt like it felt like back home in Slovakia so Andrey is now here for till end of October so for a couple
   of more weeks he would be interested in staying with us in our Airbnb from October 20th till 27th so I should
   send him a link and we could like figure it out um they stayed in like two other Airbnbs or three in Mission
   in Silver Terrace in Delhi city he's staying here with his colleague another so Marek is account executive he
    has another account but he also does like SDR stuff he said he wanted Sequoia but he got Anderson Horowitz
    they were doing coin flips on who's going to get which account and Marek likes to go to the gym and he
     mentioned that like yeah they they have the same like problem of like updating HubSpot and updating
      Marek the CEO on like what's going on in the accounts and what he was doing before was like they would
       have a conversation like uh Andrey would call Marek and tell him about like it is what happened is
       what happened but they're not like tracking it like recording it and they're not like tracking it
       like recording it anywhere although so yeah so if Andrey could just like record a voice memo and this
        could be recorded into a system that would help them a lot Andrey also says he has a great memory and he
        remembers like like the entire conversations but now he starts to feel that it's not he's also reaching
        his limits so yeah Andrey also gave me a demo of their tool and he was really good but when I commented
        on his demo demoing skills he's like no in a real demo I would give you much more discovery questions to
         learn about you to start with so it's like okay that's good to know learning about how to sell
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
        # contact_def = _gen_form_from_properties_api_response(props.results)
        # print(f"contact_def to_python_definition: {contact_def.to_python_definition()}")
        # exit()

        test_gpt_client = OpenAiClient()
        test_data_entry_id = BaseDataEntry.insert(
            account_id=test_acc.id,
            display_name=f"Data entry for {test_acc.id}",
            idempotency_id=str(time.time()),
            input_type="test",
        ).execute()

        db_task = Task.create_task("test", test_data_entry_id)
        peter_voxana_user_id = 550982168
        hs_data_entry = extract_and_sync_contact_with_follow_up(
            test_hs_client,
            test_gpt_client,
            text=test_data1,
            db_task=db_task,
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

        EmailLog.save_last_email_log_to("result-hubspot-dump.html")
