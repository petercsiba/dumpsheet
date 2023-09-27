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

    #
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

    # "industry": "which business area they specialize in professionally",
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


# Treat this a form definition
class HubspotContactDefinition:
    def __init__(self, fields: Dict[str, HubspotFieldDefinition]):
        self.fields = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS}

    @classmethod
    def from_properties_api_response(
        cls, field_list: List[ModelProperty]
    ) -> "HubspotContactDefinition":
        fields = {}
        for field_response in field_list:
            field = HubspotFieldDefinition.from_properties_api_response(field_response)
            fields[field.name] = field
        return cls(fields)

    def to_gpt_prompt(self) -> str:
        return ",\n".join([field.to_gpt_prompt() for field in self.fields.values()])


# This class will act as the value storage
class HubspotContactData:
    def __init__(
        self,
        definition: HubspotContactDefinition,
        data: SimplePublicObjectWithAssociations,
    ):
        self.definition = definition
        self.data = {}
        for field_name, value in data.properties.items():
            self.set_field_value(field_name, value)

    def set_field_value(self, field_name: str, value: Any, raise_key_error=False):
        if field_name in self.definition.fields:
            self.data[field_name] = value
        else:
            if raise_key_error:
                raise KeyError(
                    f"Field '{field_name}' does not exist on HubspotContact."
                )
