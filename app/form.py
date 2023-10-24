import datetime
from enum import Enum
from typing import Any, List, Optional, Tuple

import phonenumbers
import pytz
from dateutil import parser

from app.utils import get_local_timezone


class Option:
    def __init__(self, label, value):
        self.label = label
        self.value = value


# Treat this as a form field
# TODO(P1, devx): Make field_type an Enum
# TODO: Custom display transformations;
class FieldDefinition:
    def __init__(
        self,
        name: str,
        field_type: str,
        label: str,
        description: Optional[str] = None,
        options: Optional[List[Option]] = None,
        ignore_in_prompt: bool = False,
        custom_field: Optional[bool] = None,
        default_value: Any = None,
    ):
        self.name = name
        self.field_type = field_type
        self.label = label
        self.description = description
        self.options = options
        self.ignore_in_prompt = ignore_in_prompt
        self.custom_field = bool(custom_field)
        self.default_value = default_value

    @classmethod
    def _none_or_quoted_str(cls, value: Optional[str]) -> str:
        return f'"{value}"' if isinstance(value, str) else "None"

    @classmethod
    def _gen_options(cls, options: Optional[list[Option]]) -> str:
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
            custom_field={custom_field}
        )""".format(
            name=self.name,
            field_type=self.field_type,
            label=self.label,
            description=FieldDefinition._none_or_quoted_str(self.description),
            options=FieldDefinition._gen_options(self.options),
            custom_field=str(self.custom_field),
        )

    def _has_options(self):
        return self.field_type in ["radio", "select"]

    # TODO(ux, p1): Feels like the display_value should be outside of form.py, cause it depends on the output dest
    #   being like email, spreadsheet, app or webapp. Database / Python kinda counts too.
    def display_value(self, value):
        if value is None:
            # TODO(P0, hack): Add a FieldDefinition.required
            if self.name in ["name", "phone"]:
                return "None - Please fill in"
            return "None"

        if self._has_options():
            option_labels = {option.value: option.label for option in self.options}
            return option_labels.get(value, str(value))

        if self.field_type == "date":
            datetime_value = self._validate_date(value)

            # Convert the datetime to PST
            pst = pytz.timezone("America/Los_Angeles")
            datetime_value = datetime_value.astimezone(pst)

            # TODO(ux, P0): For spreadsheets we should output just YYYY-MM-DD HH:ii, so it's easier to sort by.
            return datetime_value.strftime("%b %d %Y, %-I%p %Z")

        # TODO(P0, hack): Add special handling on the FieldDefinition; especially HubSpot fields like ObjId can use it
        if self.name in ["firstname", "lastname"]:
            return " ".join(word.capitalize() for word in str(value).split(" "))

        return value

    def validate_and_fix(self, value: Optional[Any]) -> Any:
        if value is None:
            return None

        if str(value).lower() in ["none", "null", "unknown"]:
            return None

        # Sometimes, GPT results in entire definition of the field, in that case extra the value
        # For example:
        # Invalid format for task.hs_task_subject expected unexpected text type (type=text) given
        # { 'label': 'Task Title',
        #   'description': 'The title of the task',
        #   'type': 'text',
        #   'value': 'Schedule meeting with Andrey Yursa'
        # } (type=<class 'dict'>)
        if isinstance(value, dict):
            # NOTE: We also include "type" cause ("label", "value") happens often for Select/Radio/Option fields.
            if "label" in value and "type" in value and "value" in value:
                return self.validate_and_fix(value["value"])

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
            f"WARNING: Invalid format for field {self.name} "
            f"expected {expected} (type={self.field_type}) given {value} (type={type(value)})"
        )

    # In JavaScript, date is actually a timestamp which ideally should be human-readable and ISO 8601
    def _validate_date(self, value: Any):
        if value is None:
            return None

        if isinstance(value, datetime.datetime):
            dt_value = value
            if dt_value.tzinfo is None:
                dt_value = dt_value.replace(tzinfo=get_local_timezone())
            return dt_value

        if not isinstance(value, str):
            print(f"WARNING: Unrecognized date type {type(value)}: {value}")
            return None

        try:
            parsed_date = parser.parse(str(value))

            if (
                parsed_date.tzinfo is None
                or parsed_date.tzinfo.utcoffset(parsed_date) is None
            ):
                parsed_date = pytz.UTC.localize(parsed_date)

                pst = pytz.timezone("America/Los_Angeles")
                parsed_date = pst.localize(
                    datetime.datetime.combine(
                        parsed_date.date(), datetime.time(hour=13)
                    )
                )
                parsed_date = parsed_date.astimezone(pytz.UTC)

            return parsed_date

        except (TypeError, ValueError) as e:
            print(f"WARNING parsing date: {e}")
            self._validation_error("timestamp", value)
            return datetime.datetime.now(pytz.UTC)

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

        # And sometimes we get `'hs_task_status': ['Not Started', 'NOT_STARTED']`
        if isinstance(value, (list, tuple)):
            if len(value) == 2:
                return self._validate_select(value[1], options)
            print(
                f"WARNING: Un-expected number of list items for an options field: {value}"
            )
            return self._validate_select(value[0], options)

        self._validation_error("unexpected format", value)
        return None

    def _validate_text(self, value: Any):
        if isinstance(value, str) or value is None:
            return value

        if isinstance(value, list):
            return "\n".join(f"* {item}" for item in value)

        if isinstance(value, dict):
            return "\n".join(f"* {key}: {value}" for key, value in value.items())

        self._validation_error("unexpected text type", value)
        return str(value)


class FormName(Enum):
    NETWORKING = "networking"
    HUBSPOT_CONTACT = "hubspot_contact"
    HUBSPOT_TASK = "hubspot_task"
    HUBSPOT_MEETING = "hubspot_meeting"
    FOOD_LOG = "food_log"

    @property
    def value(self):
        return self._value_

    @staticmethod
    def from_str(str_value: str):
        for form in FormName:
            if form.value == str_value:
                return form
        return None


# Mostly used for code-gen
class FormDefinition:
    def __init__(self, form_name: FormName, fields: List[FieldDefinition]):
        # Idea: Add a GPT explanation of the form, so we can classify the voice-memo.
        self.form_name = form_name
        self.fields = fields

    def get_field(self, field_name):
        for field in self.fields:
            if field.name == field_name:
                return field

        # This function is oftentimes used to check if name is in the field list so only warning.
        # It's a bit annoying, but can be lifesaving when developing.
        print(f"WARNING: Requested field {self.form_name}.{field_name} not in list")
        return None

    def get_field_names(self) -> list[str]:
        return [field.name for field in self.fields]

    def to_python_definition(self):
        return ",\n".join([field.to_python_definition() for field in self.fields])


# Related to HubspotObject
class FormData:
    def __init__(
        self,
        form: FormDefinition,
        data: Optional[dict] = None,
        omit_unknown_fields: bool = False,
    ):
        self.form = form
        self.data = {}
        if data is None:
            data = {}

        for field_name, value in data.items():
            self.set_field_value(
                field_name, value, raise_key_error=not omit_unknown_fields
            )

        # Fill in the defaults
        for field in form.fields:
            if field.name not in data or data[field.name] is None:
                if field.default_value is not None:
                    print(
                        f"Filling in default value for {form.form_name}.{field.name} to {field.default_value}"
                    )
                    self.set_field_value(field.name, field.default_value)

    def get_field(self, field_name) -> FieldDefinition:
        return self.form.get_field(field_name)

    def get_value(self, field_name: str, default_value=None):
        return self.data[field_name] if field_name in self.data else default_value

    def get_display_value(self, field_name: str) -> str:
        field = self.get_field(field_name)
        if bool(field):
            return field.display_value(self.data.get(field_name))
        return "None"

    def set_field_value(self, field_name: str, value: Any, raise_key_error=False):
        field = self.get_field(field_name)
        if bool(field):
            self.data[field_name] = field.validate_and_fix(value)
        else:
            error = (
                f"Field '{self.form.form_name}.{field_name}' "
                f"does not exist in FormDefinition {self.form.get_field_names()}"
            )
            if raise_key_error:
                raise KeyError(error)
            else:
                print(f"WARNING: Skipping {error}")

    def to_display_tuples(self) -> List[Tuple[str, str]]:
        result = []
        for field in self.form.fields:
            result.append((field.label, self.get_display_value(field.name)))

        return result

    # TODO: We maybe want ordered dict.
    def to_dict(self) -> dict:
        return self.data.copy()
