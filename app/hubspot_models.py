import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import phonenumbers
from hubspot.crm.properties import ModelProperty, Option


# We allow-list fields which we will use with Hubspot
class FieldNames(Enum):
    # Common object fields; There are also createdate, lastmodifieddate, updated_at which we ignore.
    # HS_ACTIVITY_TYPE = "hs_activity_type"
    HS_OBJECT_ID = "hs_object_id"
    # TODO: We will need to somehow map their emails / account to HS account.
    HUBSPOT_OWNER_ID = "hubspot_owner_id"
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
    COMPANY = "company"
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


# Treat this as a form field
class FieldDefinition:
    def __init__(
        self,
        name: str,
        field_type: str,
        label: str,
        description: Optional[str] = None,
        options: Optional[List[Option]] = None,
        group_name: Optional[str] = None,
        hubspot_defined: Optional[bool] = None,
        **kwargs,
    ):
        self.name = name
        self.field_type = field_type
        self.label = label
        self.description = description
        self.options = options
        self.group_name = group_name
        self.hubspot_defined = hubspot_defined

    # Code-gen
    @classmethod
    def from_properties_api_response(cls, response: ModelProperty) -> "FieldDefinition":
        return cls(
            name=response.name,
            field_type=response.field_type,
            label=response.label,
            description=response.description,
            options=response.options,
            group_name=response.group_name,
            hubspot_defined=response.hubspot_defined,
        )

    @classmethod
    def _none_or_quoted_str(self, value: Optional[str]) -> str:
        return f'"{value}"' if isinstance(value, str) else "None"

    @classmethod
    def _gen_options(self, options: Optional[list[Option]]) -> str:
        if isinstance(options, list):
            options_definitions = [
                f'Option(label="{opt.label}", value="{opt.value}")' for opt in options
            ]
            return "[" + ",\n".join(options_definitions) + "]"
        return "None"

    # Code-gen
    def to_python_definition(self) -> str:
        return """
        "{name}": FieldDefinition(
            name="{name}",
            field_type="{field_type}",
            label="{label}",
            description={description},
            options={options},
            group_name={group_name},
            hubspot_defined={hubspot_defined}
        )""".format(
            name=self.name,
            field_type=self.field_type,
            label=self.label,
            description=FieldDefinition._none_or_quoted_str(self.description),
            options=FieldDefinition._gen_options(self.options),
            group_name=FieldDefinition._none_or_quoted_str(self.group_name),
            hubspot_defined=str(self.hubspot_defined),
        )

    def _has_options(self):
        return self.field_type in ["radio", "select"]

    def display_value(self, value):
        if not self._has_options():
            return value

        option_labels = {option.value: option.label for option in self.options}
        return option_labels.get(value, str(value))

    def validate_and_fix(self, value: Optional[Any]) -> Any:
        if value is None:
            return None

        if self.field_type == "text":
            return self._validate_text(value)
        if self.field_type == "date":
            return self._validate_date(value)
        if self.field_type == "html":
            return self._validate_html(value)
        if self.field_type == "number":
            return self._validate_number(value)
        if self.field_type == "phonenumber":
            return self._validate_phonenumber(value)
        if self._has_options():
            return self._validate_select(value, self.options)
        print(f"WARNING: No validator for field type {self.field_type}: {value}")
        return None

    def _validation_error(self, expected: str, value: Any):
        print(
            f"WARNING: Invalid {self.field_type} format for {self.group_name}.{self.name} "
            f"expected {expected} given (type={type(value)}): {value}"
        )

    def _validate_date(self, value: Any):
        try:
            datetime.datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            self._validation_error("YYYY-MM-DD", value)
            return None
        return value

    def _validate_html(self, value: Any):
        return self._validate_text(value)

    def _validate_number(self, value: Any):
        try:
            return int(value)
        except ValueError:
            self._validation_error("int", value)
            return None

    def _validate_phonenumber(self, value: Any, default_region="US"):
        try:
            parsed_number = phonenumbers.parse(value, default_region)
            if phonenumbers.is_valid_number(parsed_number):
                return phonenumbers.format_number(
                    parsed_number, phonenumbers.PhoneNumberFormat.E164
                )
            else:
                self._validation_error("invalid", value)
        except phonenumbers.phonenumberutil.NumberParseException:
            self._validation_error("cannot parse", value)

        return None

    def _validate_select(self, value: Any, options: List[Option]):
        option_values = [option.value for option in options]
        if isinstance(value, str):
            if value in option_values:
                return value
            # Sometimes GPT outputs the Label instead of the Value
            option_labels = {option.label: option.value for option in options}
            if value in option_labels:
                return option_labels[value]
            self._validation_error("str value not an option label or value ", value)

        # Sometimes we get `'hs_task_type': {'label': 'Call', 'value': 'CALL'}`
        if isinstance(value, dict):
            if "value" in value:
                return self._validate_select(value["value"], options)

        self._validation_error("unexpected format", value)
        return None

    def _validate_text(self, value: Any):
        if isinstance(value, str) or value is None:
            return value

        self._validation_error("unexpected text type", value)
        return str(value)


# Mostly used for code-gen
class FormDefinition:
    def __init__(self, fields: Dict[str, FieldDefinition]):
        # TODO(P1, correctness): I imagine we would need a GPT intro / context string
        self.fields = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS}

    @classmethod
    def from_properties_api_response(
        cls, field_list: List[ModelProperty]
    ) -> "FormDefinition":
        fields = {}
        for field_response in [f for f in field_list if f.name in ALLOWED_FIELDS]:
            field = FieldDefinition.from_properties_api_response(field_response)
            fields[field.name] = field
        return cls(fields)

    def to_python_definition(self):
        return ",\n".join(
            [field.to_python_definition() for field in self.fields.values()]
        )


# This class will act as the value storage
class HubspotObject:
    def __init__(
        self,
        form: FormDefinition,
    ):
        self.form = form
        self.data = {}  # you can just plug into properties

    @classmethod
    def from_api_response_props(
        cls,
        form: FormDefinition,
        response_props: Optional[Dict[str, Any]],
    ) -> Optional["HubspotObject"]:
        if response_props is None:
            return None

        result = HubspotObject(form)
        for field_name, value in response_props.items():
            result.set_field_value(field_name, value)
        return result

    def set_field_value(self, field_name: str, value: Any, raise_key_error=False):
        if field_name in self.form.fields.keys():
            # field: FieldDefinition = self.form.fields[field_name]
            # self.data[field_name] = field.validate_and_fix(value)
            self.data[field_name] = value
        else:
            # print(f"INFO: omitting `{field_name}` from")
            if raise_key_error:
                raise KeyError(
                    f"Field '{field_name}' does not exist on HubspotContact."
                )

    def get_value(self, field_name: str) -> str:
        return self.form.fields[field_name].display_value(self.data.get(field_name))

    def get_field_display_label_with_value(self, field_name) -> Tuple[str, Any]:
        return self.form.fields[field_name].label, self.get_value(field_name)


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


CONTACT_FIELDS = {
    "firstname": FieldDefinition(
        name="firstname",
        field_type="text",
        label="First Name",
        description="A contact's first name",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "lastname": FieldDefinition(
        name="lastname",
        field_type="text",
        label="Last Name",
        description="A contact's last name",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "email": FieldDefinition(
        name="email",
        field_type="text",
        label="Email",
        description="A contact's email address",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "phone": FieldDefinition(
        name="phone",
        field_type="phonenumber",
        label="Phone Number",
        description="A contact's primary phone number",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "hubspot_owner_id": FieldDefinition(
        name="hubspot_owner_id",
        field_type="select",
        label="Contact owner",
        description=(
            "The owner of a contact. This can be any HubSpot user or Salesforce integration user, "
            "and can be set manually or via Workflows."
        ),
        options=[],
        group_name="sales_properties",
        hubspot_defined=True,
    ),
    "city": FieldDefinition(
        name="city",
        field_type="text",
        label="City",
        description="A contact's city of residence",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "state": FieldDefinition(
        name="state",
        field_type="text",
        label="State/Region",
        description="The contact's state of residence.",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "country": FieldDefinition(
        name="country",
        field_type="text",
        label="Country/Region",
        description="The contact's country/region of residence.",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "jobtitle": FieldDefinition(
        name="jobtitle",
        field_type="text",
        label="Job Title",
        description="A contact's job title",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "lifecyclestage": FieldDefinition(
        name="lifecyclestage",
        field_type="radio",
        label="Lifecycle Stage",
        description="The qualification of contacts to sales readiness.",
        options=[
            Option(label="Subscriber", value="subscriber"),
            Option(label="Lead", value="lead"),
            Option(label="Marketing Qualified Lead", value="marketingqualifiedlead"),
            Option(label="Sales Qualified Lead", value="salesqualifiedlead"),
            Option(label="Opportunity", value="opportunity"),
            Option(label="Customer", value="customer"),
            Option(label="Evangelist", value="evangelist"),
            Option(label="Other", value="other"),
        ],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "hs_lead_status": FieldDefinition(
        name="hs_lead_status",
        field_type="radio",
        label="Lead Status",
        description="The contact's sales, prospecting or outreach status",
        options=[
            Option(label="New", value="NEW"),
            Option(label="Open", value="OPEN"),
            Option(label="In Progress", value="IN_PROGRESS"),
            Option(label="Open Deal", value="OPEN_DEAL"),
            Option(label="Unqualified", value="UNQUALIFIED"),
            Option(label="Attempted to Contact", value="ATTEMPTED_TO_CONTACT"),
            Option(label="Connected", value="CONNECTED"),
            Option(label="Bad Timing", value="BAD_TIMING"),
        ],
        group_name="sales_properties",
        hubspot_defined=True,
    ),
    "company": FieldDefinition(
        name="company",
        field_type="text",
        label="Company Name",
        description=(
            "Name of the contact's company. This can be set independently from the name property on "
            "the contact's associated company."
        ),
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "industry": FieldDefinition(
        name="industry",
        field_type="text",
        label="Industry",
        description="The Industry a contact is in",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
}

CALL_FIELDS = {
    # "hs_activity_type": FieldDefinition(
    #     name="hs_activity_type",
    #     field_type="select",
    #     label="Call and meeting type",
    #     description="The activity type of the engagement",
    #     options=[],
    #     group_name="engagement",
    #     hubspot_defined=True,
    # ),
    "hs_call_body": FieldDefinition(
        name="hs_call_body",
        field_type="html",
        label="Call notes",
        description="Summary of the call transcript, use short paragraphs or bullet points.",
        options=[],
        group_name="call",
        hubspot_defined=True,
    ),
    "hs_call_callee_object_id": FieldDefinition(
        name="hs_call_callee_object_id",
        field_type="number",
        label="Callee object id",
        description=(
            "The ID of the HubSpot record associated with the call. "
            "This will be the recipient of the call for OUTBOUND calls, or the dialer of the call for INBOUND calls."
        ),
        options=[],
        group_name="call",
        hubspot_defined=True,
    ),
    "hs_call_direction": FieldDefinition(
        name="hs_call_direction",
        field_type="select",
        label="Call direction",
        description="The direction of the call from the perspective of the HubSpot user.",
        options=[
            Option(label="Inbound", value="INBOUND"),
            Option(label="Outbound", value="OUTBOUND"),
        ],
        group_name="call",
        hubspot_defined=True,
    ),
    # TODO(P1, fullness): Seems ignored by GPT
    "hs_call_disposition": FieldDefinition(
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
        hubspot_defined=True,
    ),
    "hs_call_from_number": FieldDefinition(
        name="hs_call_from_number",
        field_type="text",
        label="From number",
        description="The phone number of the person that initiated the call",
        options=[],
        group_name="call",
        hubspot_defined=True,
    ),
    "hs_call_status": FieldDefinition(
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
        hubspot_defined=True,
    ),
    "hs_call_title": FieldDefinition(
        name="hs_call_title",
        field_type="text",
        label="Call Title",
        description="The title of the call",
        options=[],
        group_name="call",
        hubspot_defined=True,
    ),
    "hs_call_to_number": FieldDefinition(
        name="hs_call_to_number",
        field_type="text",
        label="To Number",
        description="The phone number of the person that was called",
        options=[],
        group_name="call",
        hubspot_defined=True,
    ),
    "hs_object_id": FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        group_name="callinformation",
        hubspot_defined=True,
    ),
    "hs_timestamp": FieldDefinition(
        name="hs_timestamp",
        field_type="date",
        label="Activity date",
        description="The date that an engagement occurred",
        options=[],
        group_name="engagement",
        hubspot_defined=True,
    ),
    "hubspot_owner_id": FieldDefinition(
        name="hubspot_owner_id",
        field_type="select",
        label="Activity assigned to",
        description=(
            "The user that the activity is assigned to in HubSpot. "
            "This can be any HubSpot user or Salesforce integration user, and can be set manually or via Workflows."
        ),
        options=[],
        group_name="engagement",
        hubspot_defined=True,
    ),
}

TASK_FIELDS = {
    "hs_object_id": FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        group_name="taskinformation",
        hubspot_defined=True,
    ),
    "hs_task_body": FieldDefinition(
        name="hs_task_body",
        field_type="html",
        label="Notes",
        description="Action items in short bullet points",
        options=[],
        group_name="task",
        hubspot_defined=True,
    ),
    "hs_task_priority": FieldDefinition(
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
        hubspot_defined=True,
    ),
    "hs_task_status": FieldDefinition(
        name="hs_task_status",
        field_type="select",
        label="Task Status",
        description="The status of the task",
        options=[
            Option(label="Completed", value="COMPLETED"),
            Option(label="Deferred", value="DEFERRED"),
            Option(label="In Progress", value="IN_PROGRESS"),
            Option(label="Not Started", value="NOT_STARTED"),
            Option(label="Waiting", value="WAITING"),
        ],
        group_name="task",
        hubspot_defined=True,
    ),
    "hs_task_subject": FieldDefinition(
        name="hs_task_subject",
        field_type="text",
        label="Task Title",
        description="The title of the task",
        options=[],
        group_name="task",
        hubspot_defined=True,
    ),
    "hs_task_type": FieldDefinition(
        name="hs_task_type",
        field_type="select",
        label="Task Type",
        description="The type of the task",
        options=[
            Option(label="Call", value="CALL"),
            Option(label="Email", value="EMAIL"),
            Option(label="LinkedIn", value="LINKED_IN"),
            Option(label="Meeting", value="MEETING"),
            Option(
                label="Sales Navigator - Connection Request", value="LINKED_IN_CONNECT"
            ),
            Option(label="Sales Navigator - InMail", value="LINKED_IN_MESSAGE"),
            Option(label="To Do", value="TODO"),
        ],
        group_name="task",
        hubspot_defined=True,
    ),
    "hs_timestamp": FieldDefinition(
        name="hs_timestamp",
        field_type="date",
        label="Due date",
        description="The due date of the task",
        options=[],
        group_name="engagement",
        hubspot_defined=True,
    ),
    "hubspot_owner_id": FieldDefinition(
        name="hubspot_owner_id",
        field_type="select",
        label="Assigned to",
        description=(
            "The user that the task is assigned to in HubSpot. "
            "This can be any HubSpot user or Salesforce integration user, and can be set manually or via Workflows."
        ),
        options=[],
        group_name="engagement",
        hubspot_defined=True,
    ),
}
