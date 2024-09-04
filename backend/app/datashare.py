import datetime
import json
from dataclasses import dataclass, field, fields, is_dataclass
from json import JSONEncoder
from typing import Any, List, Optional, Type, get_args, get_origin

from gpt_form_filler.form import FormData


def check_required_str(name, s):
    if s is None or len(s) == 0:
        print(f"ERROR: DataEntry invalid string {name}: {s}")


def check_required_list(name, lst):
    if lst is None or len(lst) == 0:
        print(f"ERROR: DataEntry invalid list {name}: {lst}")


class DynamoEncoder(JSONEncoder):
    def default(self, o):
        print(f"DynamoEncoder {type(o)} value: {o}")
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        # TODO(P2, devx): TypeError: Float types are not supported. Use Decimal types instead.

        return super().default(o)


#  Python's json module does not offer a built-in way to use a custom decoder class, like it does for encoding.
#  But you can use a function and pass that function to json.loads() as the object_hook parameter.
def datetime_decoder(dict_):
    for k, v in dict_.items():
        if isinstance(v, str):  # Check if the value is string
            try:
                # Try to parse a datetime from the string
                dict_[k] = datetime.datetime.fromisoformat(v)
            except ValueError:
                pass
    return dict_


def dict_to_dataclass(dict_: dict, dataclass_type: Type[Any]) -> dataclass:
    if dict_ is None:
        print(f"No data found for {dataclass_type}, trying to instantiate an empty one")
        return dataclass_type()

    if not isinstance(dict_, dict):
        print(
            f"WARNING: dict_to_dataclass expected a dict, given {type(dict_)} for {dict_}"
        )
        return dataclass_type()

    init_values = {}
    # noinspection PyDataclass
    for f in fields(dataclass_type):
        value = dict_.get(f.name)  # e.g. None might be NOT set
        # GPT generated magic to handle List[DataClass] parsing.
        field_args = get_args(f.type)
        if (
            get_origin(f.type) is list
            and len(field_args) == 1
            and is_dataclass(field_args[0])
        ):
            sub_dataclass_type = field_args[0]
            list_of_dataclass = []
            # Now for each element of the list, which is expected to be a dataclass, parse it from the expected dict
            for val in value:
                # This also handles None
                list_of_dataclass.append(dict_to_dataclass(val, sub_dataclass_type))
            init_values[f.name] = list_of_dataclass
        # Handle single sub-dataclass case
        elif is_dataclass(f.type):
            init_values[f.name] = dict_to_dataclass(value, f.type)
        else:
            init_values[f.name] = value
    return dataclass_type(**init_values)


def json_to_dataclass(json_data, data_class_type: Type[Any]) -> dataclass:
    dict_ = json.loads(json_data, object_hook=datetime_decoder)
    return dict_to_dataclass(dict_, data_class_type)


def dump_to_lines(sth_like_a_string, sep="\n") -> str:
    if sth_like_a_string is None:
        return ""
    elif isinstance(sth_like_a_string, str):
        return sth_like_a_string
    elif isinstance(sth_like_a_string, list):  # Check if follow_ups is a list
        return sep.join([dump_to_lines(x, sep) for x in sth_like_a_string])
    elif isinstance(sth_like_a_string, dict):  # Check if follow_ups is a dictionary
        return sep.join(
            f"{str(key)}: {str(value)}" for key, value in sth_like_a_string.items()
        )
    else:
        return str(sth_like_a_string)


# TODO(P0): Migrate this to the Task object, the Person should be inside task.context
#   One day we will formalize it more.
@dataclass
# These are pre-merged snapshots of a person
class PersonDataEntry:
    # Main identifier
    name: str = None

    # INPUTS
    # All text mentioning them joined into one string
    transcript: str = None  # TODO: Deprecate in favor of `note`

    # TODO(P1, devx): These fields might be NOT necessary just afraid to delete RN,
    # - as migrating this object to form_data slowly.
    role: str = None
    industry: str = None
    suggested_revisit: str = "P2(later)"
    # Explicitly mentioned actions to take
    key_facts: List[str] = field(default_factory=list)
    my_action_items: List[str] = field(default_factory=list)
    suggested_response_item: str = None
    summarized_note: str = ""
    response_message_type: str = "sms"  # TODO: make this an enum
    their_needs: List[str] = field(default_factory=list)

    # These are actual copy-paste-able drafts from the mentioned follow-ups, hard coded list and such
    next_draft: Optional[str] = None

    parsing_error: str = None
    # Fields which will be synced to Spreadsheets
    form_data: Optional[FormData] = None

    def get_transcript_text(self, separator="\n") -> str:  # TODO: Deprecated with GPT-4
        return dump_to_lines(self.transcript, separator)

    def sort_key(self):
        return 0 if self.should_show_full_contact_card() else 1, -len(
            str(self.transcript)
        )

    def should_draft(self):
        return self.should_show_full_contact_card() and bool(
            self.suggested_response_item
        )

    def should_show_full_contact_card(self):
        return not bool(self.parsing_error)
