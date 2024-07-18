# TODO(P1, reliability): Some fields are required while can be hard to GPT generate - we should default set.
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.form_library import HUBSPOT_CALL_FIELDS
from common.form import FieldDefinition, FormDefinition


# We allow-list fields which we will use with Hubspot
class FieldNames(Enum):
    # Common object fields; There are also createdate, lastmodifieddate, updated_at which we ignore.
    # HS_ACTIVITY_TYPE = "hs_activity_type"
    HS_OBJECT_ID = "hs_object_id"
    HUBSPOT_OWNER_ID = (
        "hubspot_owner_id"  # NOTE: Stored as `str` in the DB, while presented as `int`.
    )
    HS_TIMESTAMP = "hs_timestamp"
    # Contact: Top-level
    EMAIL = "email"
    FIRSTNAME = "firstname"
    LASTNAME = "lastname"
    PHONE = "phone"
    CITY = "city"
    STATE = "state"
    COUNTRY = "country"
    # Contact: Job info
    COMPANY = "company"  # NOTE: WOW, HubSpot prospecting tool has a database of companies which gets auto-filled.
    JOBTITLE = "jobtitle"
    INDUSTRY = "industry"
    # Contact: Lifecycle and Marketing
    LIFECYCLESTAGE = "lifecyclestage"
    HS_LEAD_STATUS = "hs_lead_status"
    # RECENT_CONVERSION_EVENT_NAME = "recent_conversion_event_name"  # property is a calculated value, cannot be set
    # Calls:
    HS_CALL_BODY = "hs_call_body"
    HS_CALL_CALLEE_OBJECT_ID = "hs_call_callee_object_id"
    HS_CALL_CALLEE_OBJECT_TYPE_ID = "hs_call_callee_object_type_id"
    HS_CALL_DIRECTION = "hs_call_direction"
    HS_CALL_DISPOSITION = "hs_call_disposition"
    HS_CALL_FROM_NUMBER = "hs_call_from_number"
    HS_CALL_STATUS = "hs_call_status"
    HS_CALL_TITLE = "hs_call_title"
    HS_CALL_TO_NUMBER = "hs_call_to_number"
    # Tasks
    HS_TASK_BODY = "hs_task_body"
    HS_TASK_SUBJECT = "hs_task_subject"
    HS_TASK_STATUS = "hs_task_status"
    HS_TASK_PRIORITY = "hs_task_priority"
    HS_TASK_TYPE = "hs_task_type"


ALLOWED_FIELDS = set(item.value for item in FieldNames)


# TODO(P1, devx): Create an Enum with the need for ".value"
class AssociationType(Enum):
    # Contact to object
    CONTACT_TO_COMPANY = 279
    CONTACT_TO_COMPANY_PRIMARY = 1
    CONTACT_TO_DEAL = 4
    CONTACT_TO_TICKET = 15
    CONTACT_TO_CALL = 193
    CONTACT_TO_EMAIL = 197
    CONTACT_TO_MEETING = 199
    CONTACT_TO_NOTE = 201
    CONTACT_TO_TASK = 203
    CONTACT_TO_COMMUNICATION = 82
    CONTACT_TO_POSTAL_MAIL = 454

    # Company to object
    COMPANY_TO_CONTACT = 280
    COMPANY_TO_CONTACT_PRIMARY = 2
    COMPANY_TO_DEAL = 342
    COMPANY_TO_DEAL_PRIMARY = 6
    COMPANY_TO_TICKET = 340
    COMPANY_TO_TICKET_PRIMARY = 25
    COMPANY_TO_CALL = 181
    COMPANY_TO_EMAIL = 185
    COMPANY_TO_MEETING = 187
    COMPANY_TO_NOTE = 189
    COMPANY_TO_TASK = 191
    COMPANY_TO_COMMUNICATION = 88
    COMPANY_TO_POSTAL_MAIL = 460

    # Deal to object
    DEAL_TO_CONTACT = 3
    DEAL_TO_COMPANY = 341
    DEAL_TO_COMPANY_PRIMARY = 5
    DEAL_TO_TICKET = 27
    DEAL_TO_CALL = 205
    DEAL_TO_EMAIL = 209
    DEAL_TO_MEETING = 211
    DEAL_TO_NOTE = 213
    DEAL_TO_TASK = 215
    DEAL_TO_COMMUNICATION = 86
    DEAL_TO_POSTAL_MAIL = 458

    # Ticket to object
    TICKET_TO_CONTACT = 16
    TICKET_TO_COMPANY = 339
    TICKET_TO_COMPANY_PRIMARY = 26
    TICKET_TO_DEAL = 28
    TICKET_TO_CALL = 219
    TICKET_TO_EMAIL = 223
    TICKET_TO_MEETING = 225
    TICKET_TO_NOTE = 227
    TICKET_TO_TASK = 229
    TICKET_TO_COMMUNICATION = 84
    TICKET_TO_POSTAL_MAIL = 456


def _get_field(fields: List[FieldDefinition], name: str):
    for field in fields:
        if field.name == name:
            return field

    # This function is oftentimes used to check if name is in the field list so only warning.
    # It's a bit annoying, but can be lifesaving when developing.
    print(f"WARNING: Requested field {name} not in list")
    return None


class ObjectType(Enum):
    CONTACT = "0-1"
    COMPANY = "0-2"
    TASK = "0-27"
    CALL = "0-48"


# This class will act as the value storage
# TODO(P1, devx): This starts to feel like FormData, once HubSpot becomes important again we can think of refactor
#  - would need some custom display transformers for e.g. get_link.
class HubspotObject:
    def __init__(
        self,
        hub_id: Optional[str],
        object_type: ObjectType,
        form: FormDefinition,
    ):
        self.hub_id = None
        try:
            if hub_id is not None:
                self.hub_id = int(hub_id)
        except ValueError as e:
            print(f"WARNING: invalid hub_id {hub_id} given, expected int: {e}")

        self.object_type = object_type
        self.form = form
        self.data = {}  # you can just plug into properties

    @classmethod
    def from_api_response_props(
        cls,
        hub_id: Optional[str],
        object_type: ObjectType,
        form: FormDefinition,
        response_props: Optional[Dict[str, Any]],
    ) -> Optional["HubspotObject"]:
        if response_props is None:
            return None

        # Hubspot response has many more fields than what we care about - so this will end up ignoring a bunch.
        result = HubspotObject(hub_id=hub_id, object_type=object_type, form=form)
        for field_name, value in response_props.items():
            result.set_field_value(field_name, value)
        return result

    def get_field(self, field_name):
        return _get_field(self.form.fields, field_name)

    def set_field_value(self, field_name: str, value: Any, raise_key_error=False):
        field = self.get_field(field_name)
        if bool(field):
            self.data[field_name] = value
        else:
            # print(f"INFO: omitting `{field_name}` from")
            if raise_key_error:
                raise KeyError(
                    f"Field '{field_name}' does not exist on HubspotContact."
                )

    def get_display_value(self, field_name: str) -> str:
        field = self.get_field(field_name)
        if bool(field):
            return field.display_value(self.data.get(field_name))
        return "None"

    def get_field_display_label_with_value(self, field_name: str) -> Tuple[str, Any]:
        value = None
        if field_name == FieldNames.HS_OBJECT_ID.value:
            # TODO(P2, devx): This should be outside of here, but the complexity is getting harder to manage
            link_href = self.get_link()
            if bool(link_href):
                value = f'<a href="{self.get_link()}">{self.get_display_value(field_name)} - See in Hubspot (Web)</a>'

        if value is None:
            value = self.get_display_value(field_name)

        return self.get_field(field_name).label, value

    def get_link(self) -> Optional[str]:
        if self.hub_id is None:
            return None

        object_id = self.get_display_value(FieldNames.HS_OBJECT_ID.value)
        if self.object_type == ObjectType.CONTACT:
            # Task actually cannot be linked - it only really works for contacts.
            return f"https://app.hubspot.com/contacts/{self.hub_id}/record/0-1/{object_id}/view/1"

        # TODO(P2, ux): Once we figure it out we can add it back
        # object_id = self.get_display_value(FieldNames.HS_OBJECT_ID.value)
        # if bool(object_id):
        #     return f"https://app.hubspot.com/contacts/{self.hub_id}/record/{self.object_type.value}/{object_id}/"

        return None


# Poor mans test
if __name__ == "__main__":
    ts_field = _get_field(HUBSPOT_CALL_FIELDS, "hs_timestamp")
    print("validate: " + str(ts_field.validate_and_fix("2023-10-01T00:00:00.000Z")))
    print("display_value: " + ts_field.display_value("2023-10-01T00:00:00.000Z"))

    select_field = _get_field(HUBSPOT_CALL_FIELDS, "hs_task_status")
    print(
        "validate: "
        + str(select_field.validate_and_fix(["Not Started", "NOT_STARTED"]))
    )
