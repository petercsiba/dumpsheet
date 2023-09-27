from enum import Enum
from typing import Any, Dict, List, Optional

from hubspot.crm.contacts import SimplePublicObjectWithAssociations
from hubspot.crm.properties import ModelProperty, Option


class HubspotContactFieldNames(Enum):
    # Top-level
    EMAIL = "email"
    FIRSTNAME = "firstname"
    LASTNAME = "lastname"
    PHONE = "phone"
    CITY = "city"
    STATE = "state"
    COUNTRY = "country"
    # Job info
    COMPANY = "company"
    JOBTITLE = "jobtitle"
    INDUSTRY = "industry"
    # Lifecycle and Marketing
    LIFECYCLESTAGE = "lifecyclestage"
    LEADSTATUS = "leadstatus"
    RECENT_CONVERSION_EVENT_NAME = "recent_conversion_event_name"
    HUBSPOT_OWNER_ID = "hubspot_owner_id"  # TODO: We will need to somehow map their emails / account to HS account.


ALLOWED_FIELDS = set(item.value for item in HubspotContactFieldNames)
GPT_MAX_NUM_OPTION_FIELDS = 10


# Treat this as a form field
class HubspotFieldDefinition:
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
    def to_gpt_prompt(self) -> str:
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
    def from_properties_api_response(
        cls, response: ModelProperty
    ) -> "HubspotFieldDefinition":
        # print(f"structure of field response ({type(response).__name__}): {dir(response)}")
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
    def _none_or_list(self, value: Optional[List]) -> str:
        if isinstance(value, list):
            options = [f'"{opt.value}"' for opt in value]
            return f"[{', '.join(options)}]"
        return "None"

    # Code-gen
    def to_python_definition(self) -> str:
        return """
        "{name}": HubspotFieldDefinition(
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
            description=HubspotFieldDefinition._none_or_quoted_str(self.description),
            options=HubspotFieldDefinition._none_or_list(self.options),
            group_name=HubspotFieldDefinition._none_or_quoted_str(self.group_name),
            hubspot_defined=str(self.hubspot_defined),
        )


# Mostly used for code-gen
class HubspotFormDefinition:
    def __init__(self, fields: Dict[str, HubspotFieldDefinition]):
        self.fields = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS}

    @classmethod
    def from_properties_api_response(
        cls, field_list: List[ModelProperty]
    ) -> "HubspotFormDefinition":
        fields = {}
        for field_response in field_list:
            field = HubspotFieldDefinition.from_properties_api_response(field_response)
            fields[field.name] = field
        return cls(fields)

    def to_gpt_prompt(self) -> str:
        return ",\n".join([field.to_gpt_prompt() for field in self.fields.values()])

    def to_python_definition(self):
        return ",\n".join(
            [field.to_python_definition() for field in self.fields.values()]
        )


# This class will act as the value storage
class HubspotObject:
    def __init__(
        self,
        obj_name: str,
        fields: Dict[str, HubspotFieldDefinition],
    ):
        # TODO(p0, devx): We somehow should store hs_object_id, but omit from GPT gen. Likely we need another param.
        self.obj_name = obj_name
        self.fields = fields
        self.data = {}  # you can just plug into properties

    @classmethod
    def from_api_response(
        cls,
        obj_name: str,
        fields: Dict[str, HubspotFieldDefinition],
        response: SimplePublicObjectWithAssociations,
    ):
        result = HubspotObject(obj_name, fields)
        for field_name, value in response.properties.items():
            result.set_field_value(field_name, value)
        return result

    def set_field_value(self, field_name: str, value: Any, raise_key_error=False):
        if field_name in self.fields.keys():
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
    "recent_conversion_event_name": HubspotFieldDefinition(
        name="recent_conversion_event_name",
        field_type="text",
        label="Recent Conversion",
        description="The last form this contact submitted",
        options=[],
        group_name="conversioninformation",
        hubspot_defined=True,
    ),
    "firstname": HubspotFieldDefinition(
        name="firstname",
        field_type="text",
        label="First Name",
        description="A contact's first name",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "lastname": HubspotFieldDefinition(
        name="lastname",
        field_type="text",
        label="Last Name",
        description="A contact's last name",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "email": HubspotFieldDefinition(
        name="email",
        field_type="text",
        label="Email",
        description="A contact's email address",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "phone": HubspotFieldDefinition(
        name="phone",
        field_type="phonenumber",
        label="Phone Number",
        description="A contact's primary phone number",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "hubspot_owner_id": HubspotFieldDefinition(
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
    "city": HubspotFieldDefinition(
        name="city",
        field_type="text",
        label="City",
        description="A contact's city of residence",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "state": HubspotFieldDefinition(
        name="state",
        field_type="text",
        label="State/Region",
        description="The contact's state of residence. This might be set via import, form, or integration.",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "country": HubspotFieldDefinition(
        name="country",
        field_type="text",
        label="Country/Region",
        description="The contact's country/region of residence. This might be set via import, form, or integration.",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "jobtitle": HubspotFieldDefinition(
        name="jobtitle",
        field_type="text",
        label="Job Title",
        description="A contact's job title",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "lifecyclestage": HubspotFieldDefinition(
        name="lifecyclestage",
        field_type="radio",
        label="Lifecycle Stage",
        description=(
            "The qualification of contacts to sales readiness. It can be set through imports, forms, workflows"
            ", and manually on a per contact basis."
        ),
        options=[
            "subscriber",
            "lead",
            "marketingqualifiedlead",
            "salesqualifiedlead",
            "opportunity",
            "customer",
            "evangelist",
            "other",
        ],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
    "company": HubspotFieldDefinition(
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
    "industry": HubspotFieldDefinition(
        name="industry",
        field_type="text",
        label="Industry",
        description="The Industry a contact is in",
        options=[],
        group_name="contactinformation",
        hubspot_defined=True,
    ),
}
