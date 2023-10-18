# TODO(P1, reliability): Some fields are required while can be hard to GPT generate - we should default set.
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.form import FieldDefinition, FormDefinition, Option


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
GPT_MAX_NUM_OPTION_FIELDS = 10
GPT_IGNORE_LIST = [
    FieldNames.HS_OBJECT_ID.value,
    FieldNames.HUBSPOT_OWNER_ID.value,
    FieldNames.HS_CALL_CALLEE_OBJECT_ID,
    FieldNames.HS_CALL_FROM_NUMBER,
]


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


CONTACT_FIELDS = [
    FieldDefinition(
        name="hubspot_owner_id",
        field_type="number",
        label="Contact owner",
        description=(
            "The owner of a contact. This can be any HubSpot user or Salesforce integration user, "
            "and can be set manually or via Workflows."
        ),
        options=[],
        group_name="sales_properties",
        custom_field=False,
    ),
    FieldDefinition(
        name="firstname",
        field_type="text",
        label="First Name",
        description="Contacts first name (not surname)",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="lastname",
        field_type="text",
        label="Last Name",
        description="Contacts last name (not given name)",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="jobtitle",
        field_type="text",
        label="Job Title",
        description="A contact's job title",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="company",
        field_type="text",
        label="Company Name",
        description=(
            "Name of the contact's company. This can be set independently from the name property on "
            "the contact's associated company."
        ),
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="industry",
        field_type="text",
        label="Industry",
        description="The Industry a contact is in",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    # NOTE: Unclear what are the rules to decide
    # FieldDefinition(
    #     name="lifecyclestage",
    #     field_type="radio",
    #     label="Lifecycle Stage",
    #     description="The qualification of contacts to sales readiness.",
    #     options=[
    #         Option(label="Subscriber", value="subscriber"),
    #         Option(label="Lead", value="lead"),
    #         Option(label="Marketing Qualified Lead", value="marketingqualifiedlead"),
    #         Option(label="Sales Qualified Lead", value="salesqualifiedlead"),
    #         Option(label="Opportunity", value="opportunity"),
    #         Option(label="Customer", value="customer"),
    #         Option(label="Evangelist", value="evangelist"),
    #         Option(label="Other", value="other"),
    #     ],
    #     group_name="contactinformation",
    #     custom_field=False,
    # ),
    # NOTE: Unclear what are the rules to assign
    # FieldDefinition(
    #     name="hs_lead_status",
    #     field_type="radio",
    #     label="Lead Status",
    #     description="The contact's sales, prospecting or outreach status",
    #     options=[
    #         Option(label="New", value="NEW"),
    #         Option(label="Open", value="OPEN"),
    #         Option(label="In Progress", value="IN_PROGRESS"),
    #         Option(label="Open Deal", value="OPEN_DEAL"),
    #         Option(label="Unqualified", value="UNQUALIFIED"),
    #         Option(label="Attempted to Contact", value="ATTEMPTED_TO_CONTACT"),
    #         Option(label="Connected", value="CONNECTED"),
    #         Option(label="Bad Timing", value="BAD_TIMING"),
    #     ],
    #     group_name="sales_properties",
    #     custom_field=False,
    # ),
    FieldDefinition(
        name="email",
        field_type="text",
        label="Email",
        description="A contact's email address",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="phone",
        field_type="phonenumber",
        label="Phone Number",
        description="A contact's primary phone number",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="city",
        field_type="text",
        label="City",
        description="A contact's city of residence",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="state",
        field_type="text",
        label="State/Region",
        description="The contact's state of residence.",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="country",
        field_type="text",
        label="Country/Region",
        description="The contact's country/region of residence.",
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        group_name="contactinformation",
        custom_field=False,
    ),
]

CALL_FIELDS = [
    # "hs_activity_type": FieldDefinition(
    #     name="hs_activity_type",
    #     field_type="select",
    #     label="Call and meeting type",
    #     description="The activity type of the engagement",
    #     options=[],
    #     group_name="engagement",
    #     hubspot_defined=True,
    # ),
    FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        group_name="callinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="hubspot_owner_id",
        field_type="number",
        label="Activity assigned to",
        description=(
            "The user that the activity is assigned to in HubSpot. "
            "This can be any HubSpot user or Salesforce integration user, and can be set manually or via Workflows."
        ),
        options=[],
        group_name="engagement",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_callee_object_id",
        field_type="number",
        label="Callee object id",
        description=(
            "The ID of the HubSpot record associated with the call. "
            "This will be the recipient of the call for OUTBOUND calls, or the dialer of the call for INBOUND calls."
        ),
        options=[],
        group_name="call",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_direction",
        field_type="select",
        label="Call direction",
        description="The direction of the call from the perspective of the HubSpot user.",
        options=[
            Option(label="Inbound", value="INBOUND"),
            Option(label="Outbound", value="OUTBOUND"),
        ],
        group_name="call",
        custom_field=False,
    ),
    # TODO(P1, fullness): Seems ignored by GPT
    FieldDefinition(
        name="hs_call_disposition",
        field_type="select",
        label="Call outcome",
        description="The outcome of the call",
        options=[
            Option(label="Busy", value="9d9162e7-6cf3-4944-bf63-4dff82258764"),
            Option(label="Connected", value="f240bbac-87c9-4f6e-bf70-924b57d47db"),
            Option(
                label="Left live message", value="a4c4c377-d246-4b32-a13b-75a56a4cd0ff"
            ),
            Option(
                label="Left voicemail", value="b2cf5968-551e-4856-9783-52b3da59a7d0"
            ),
            Option(label="No answer", value="73a0d17f-1163-4015-bdd5-ec830791da20"),
            Option(label="Wrong number", value="17b47fee-58de-441e-a44c-c6300d46f273"),
        ],
        group_name="call",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_from_number",
        field_type="text",
        label="From number",
        description="The phone number of the person that initiated the call",
        options=[],
        group_name="call",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_status",
        field_type="select",
        label="Call status",
        description="The status of the call",
        options=[
            Option(label="Busy", value="BUSY"),
            Option(label="Calling CRM User", value="CALLING_CRM_USER"),
            Option(label="Canceled", value="CANCELED"),
            Option(label="Completed", value="COMPLETED"),
            Option(label="Connecting", value="CONNECTING"),
            Option(label="Failed", value="FAILED"),
            Option(label="In Progress", value="IN_PROGRESS"),
            Option(label="Missed", value="MISSED"),
            Option(label="No Answer", value="NO_ANSWER"),
            Option(label="Queued", value="QUEUED"),
            Option(label="Ringing", value="RINGING"),
        ],
        group_name="call",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_title",
        field_type="text",
        label="Call Title",
        description="The title of the call",
        options=[],
        group_name="call",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_to_number",
        field_type="text",
        label="To Number",
        description="The phone number of the person that was called",
        options=[],
        group_name="call",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_timestamp",
        field_type="date",
        label="Activity date",
        description="The date that an engagement occurred",
        options=[],
        group_name="engagement",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_body",
        field_type="html",
        label="Call notes",
        description="""
        A concise structured summary of the entire transcript,
        make sure to include all facts, if needed label those facts
        so I can review this in a year and know what happened.
        For better readability, use html paragraphs and bullet points.
        """,
        options=[],
        group_name="call",
        custom_field=False,
    ),
]

# https://community.hubspot.com/t5/APIs-Integrations/Create-TASK-engagement-with-due-date-and-reminder-via-API/m-p/235759#M14655
TASK_FIELDS = [
    FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        group_name="taskinformation",
        custom_field=False,
    ),
    FieldDefinition(
        name="hubspot_owner_id",
        field_type="number",
        label="Assigned to",
        description=(
            "The user that the task is assigned to in HubSpot. "
            "This can be any HubSpot user or Salesforce integration user, and can be set manually or via Workflows."
        ),
        options=[],
        group_name="engagement",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_task_subject",
        field_type="text",
        label="Task Title",
        description="The title of the task",
        options=[],
        group_name="task",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_task_priority",
        field_type="select",
        label="Priority",
        description="The priority of the task",
        options=[
            Option(label="None", value="NONE"),
            Option(label="Low", value="LOW"),
            Option(label="Medium", value="MEDIUM"),
            Option(label="High", value="HIGH"),
        ],
        group_name="task",
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_timestamp",
        field_type="date",
        label="Due date",
        description="The due date of the task",
        options=[],
        group_name="engagement",
        custom_field=False,
    ),
    # NOTE: The user should set this
    # FieldDefinition(
    #     name="hs_task_status",
    #     field_type="select",
    #     label="Task Status",
    #     description="The status of the task",
    #     options=[
    #         Option(label="Completed", value="COMPLETED"),
    #         Option(label="Deferred", value="DEFERRED"),
    #         Option(label="In Progress", value="IN_PROGRESS"),
    #         Option(label="Not Started", value="NOT_STARTED"),
    #         Option(label="Waiting", value="WAITING"),
    #     ],
    #     group_name="task",
    #     custom_field=False,
    # ),
    # NOTE: Unclear how is this derived
    # FieldDefinition(
    #     name="hs_task_type",
    #     field_type="select",
    #     label="Task Type",
    #     description="The type of the task",
    #     options=[
    #         Option(label="Call", value="CALL"),
    #         Option(label="Email", value="EMAIL"),
    #         Option(label="LinkedIn", value="LINKED_IN"),
    #         Option(label="Meeting", value="MEETING"),
    #         Option(
    #             label="Sales Navigator - Connection Request", value="LINKED_IN_CONNECT"
    #         ),
    #         Option(label="Sales Navigator - InMail", value="LINKED_IN_MESSAGE"),
    #         Option(label="To Do", value="TODO"),
    #     ],
    #     group_name="task",
    #     custom_field=False,
    # ),
    FieldDefinition(
        name="hs_task_body",
        field_type="html",
        label="To Dos",
        description="Action items and follows ups I need to do in concise bullet points ordered by priority top down",
        options=[],
        group_name="task",
        custom_field=False,
    ),
]

# Poor mans test
if __name__ == "__main__":
    ts_field = _get_field(CALL_FIELDS, "hs_timestamp")
    print("validate: " + str(ts_field.validate_and_fix("2023-10-01T00:00:00.000Z")))
    print("display_value: " + ts_field.display_value("2023-10-01T00:00:00.000Z"))

    select_field = _get_field(TASK_FIELDS, "hs_task_status")
    print(
        "validate: "
        + str(select_field.validate_and_fix(["Not Started", "NOT_STARTED"]))
    )
