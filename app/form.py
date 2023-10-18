import datetime
from typing import Any, List, Optional

import phonenumbers
import pytz
from dateutil import parser


class Option:
    def __init__(self, label, value):
        self.label = label
        self.value = value


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
        custom_field: Optional[bool] = None,
    ):
        self.name = name
        self.field_type = field_type
        self.label = label
        self.description = description
        self.options = options
        self.group_name = group_name
        self.custom_field = custom_field

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
            group_name={group_name},
            custom_field={custom_field}
        )""".format(
            name=self.name,
            field_type=self.field_type,
            label=self.label,
            description=FieldDefinition._none_or_quoted_str(self.description),
            options=FieldDefinition._gen_options(self.options),
            group_name=FieldDefinition._none_or_quoted_str(self.group_name),
            custom_field=str(self.custom_field),
        )

    def _has_options(self):
        return self.field_type in ["radio", "select"]

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

            return datetime_value.strftime("%b %d %Y, %-I%p %Z")

        # TODO(P0, hack): Add special handling on the FieldDefinition; especially HubSpot fields like ObjId can use it
        if self.name in ["firstname", "lastname"]:
            return " ".join(word.capitalize() for word in str(value).split(" "))

        return value

    def validate_and_fix(self, value: Optional[Any]) -> Any:
        if value is None:
            return None

        if value == "None" or value == "null":
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
            f"WARNING: Invalid format for {self.group_name}.{self.name} "
            f"expected {expected} (type={self.field_type}) given {value} (type={type(value)})"
        )

    # In JavaScript, date is actually a timestamp which ideally should be human-readable and ISO 8601
    def _validate_date(self, value: Any):
        if value is None:
            return None

        try:
            parsed_date = parser.parse(value)

            if (
                parsed_date.tzinfo is None
                or parsed_date.tzinfo.utcoffset(parsed_date) is None
            ):
                # Localize the naive datetime to UTC
                parsed_date = pytz.UTC.localize(parsed_date)

                # Convert to 1pm PST
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
            # If parsing fails or input is None, default to the current date-time in UTC
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

        self._validation_error("unexpected text type", value)
        return str(value)


# Mostly used for code-gen
class FormDefinition:
    def __init__(self, fields: List[FieldDefinition]):
        # Idea: Add a GPT explanation of the form, so we can classify the voice-memo.
        self.fields = fields

    def get_field(self, field_name):
        for field in self.fields:
            if field.name == field_name:
                return field

        # This function is oftentimes used to check if name is in the field list so only warning.
        # It's a bit annoying, but can be lifesaving when developing.
        print(f"WARNING: Requested field {field_name} not in list")
        return None

    def to_python_definition(self):
        return ",\n".join([field.to_python_definition() for field in self.fields])
