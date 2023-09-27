from enum import Enum
from typing import Any, Dict, List, Optional

from hubspot.crm.contacts import SimplePublicObjectWithAssociations
from hubspot.crm.properties import ModelProperty, Option


# We allow-list fields which we will use with Hubspot
class FieldNames(Enum):
    # Common object fields; There are also createdate, lastmodifieddate, updated_at which we ignore.
    HS_OBJECT_ID = "hs_object_id"
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
    LEADSTATUS = "leadstatus"
    RECENT_CONVERSION_EVENT_NAME = "recent_conversion_event_name"
    HUBSPOT_OWNER_ID = "hubspot_owner_id"  # TODO: We will need to somehow map their emails / account to HS account.


ALLOWED_FIELDS = set(item.value for item in FieldNames)
GPT_MAX_NUM_OPTION_FIELDS = 10
GPT_IGNORE_LIST = [FieldNames.HS_OBJECT_ID.value]


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

    # Main reason to separate Definition from Values is that we can generate GPT prompts in a generic-ish way.
    # Sample output "industry": "which business area they specialize in professionally",
    def to_gpt_prompt(self) -> Optional[str]:
        if self.name in GPT_IGNORE_LIST:
            print(f"ignoring {self.name} for gpt prompt gen")
            return None

        result = f'"{self.name}": "optional {self.field_type} value representing {self.label}'

        if bool(self.description):
            result += f" described as {self.description}"
        if bool(self.options) and isinstance(self.options, list):
            if len(self.options) > GPT_MAX_NUM_OPTION_FIELDS:
                print(f"too many options, shortening to {GPT_MAX_NUM_OPTION_FIELDS}")
            options_slice: List[Option] = self.options[:GPT_MAX_NUM_OPTION_FIELDS]
            option_values = [opt.value for opt in options_slice]
            result += f" with options as {option_values}"
        result += '"'

        return result

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

    def to_gpt_prompt(self) -> str:
        field_prompts = [field.to_gpt_prompt() for field in self.fields.values()]
        return ",\n".join([f for f in field_prompts if f is not None])

    def to_python_definition(self):
        return ",\n".join(
            [field.to_python_definition() for field in self.fields.values()]
        )


# This class will act as the value storage
class HubspotObject:
    def __init__(
        self,
        obj_name: str,
        form: FormDefinition,
    ):
        self.obj_name = obj_name
        self.form = form
        self.data = {}  # you can just plug into properties

    @classmethod
    def from_api_response(
        cls,
        obj_name: str,
        fields: Dict[str, FieldDefinition],
        response: SimplePublicObjectWithAssociations,
    ):
        result = HubspotObject(obj_name, FormDefinition(fields))
        for field_name, value in response.properties.items():
            result.set_field_value(field_name, value)
        return result

    def set_field_value(self, field_name: str, value: Any, raise_key_error=False):
        if field_name in self.form.fields.keys():
            # TODO(P1, consistency): We can use field.field_type to validate input type.
            self.data[field_name] = value
        else:
            if raise_key_error:
                raise KeyError(
                    f"Field '{field_name}' does not exist on HubspotContact."
                )


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
    "recent_conversion_event_name": FieldDefinition(
        name="recent_conversion_event_name",
        field_type="text",
        label="Recent Conversion",
        description="The last form this contact submitted",
        options=[],
        group_name="conversioninformation",
        hubspot_defined=True,
    ),
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
        description="The contact's state of residence. This might be set via import, form, or integration.",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "country": FieldDefinition(
        name="country",
        field_type="text",
        label="Country/Region",
        description="The contact's country/region of residence. This might be set via import, form, or integration.",
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
        description=(
            "The qualification of contacts to sales readiness. "
            "It can be set through imports, forms, workflows, and manually on a per contact basis."
        ),
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
