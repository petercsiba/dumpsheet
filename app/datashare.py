import datetime
import json
from dataclasses import dataclass, field, fields, is_dataclass
from json import JSONEncoder
from typing import Any, Dict, List, Type, get_args, get_origin


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


@dataclass()
class Draft:
    intent: str
    message: str


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
    # TODO(P1, devx): This seems to actually by List[str]
    transcript: str = None

    # OUTPUTS
    # Additional structured  items
    mnemonic: str = None
    mnemonic_explanation: str = None
    vibes: str = None
    role: str = None
    industry: str = None
    priority: str = None
    # Explicitly mentioned actions to take
    follow_ups: List[str] = field(default_factory=list)
    # Future-looking feature
    needs: List[str] = field(default_factory=list)
    # For everything else interesting, their children names, where are they from, what they like
    additional_metadata: Dict[str, any] = field(default_factory=dict)

    # These are actual copy-paste-able drafts from the mentioned follow-ups, hard coded list and such
    drafts: List[Draft] = field(default_factory=list)

    parsing_error: str = None

    # Katka really wants text priorities
    PRIORITIES_MAPPING = {
        5: "P0 - DO IT ASAP!",
        4: "P1 - High: This is important & needed",
        3: "P2 - Medium: Nice to have",
        2: "P3 - Unsure: Check if you have time",
        1: "P4 - Low: Just don't bother",
    }

    def get_transcript_text(self, separator="\n") -> str:
        return dump_to_lines(self.transcript, separator)

    def sort_key(self):
        # Sort by priority ascending, and transcript length descending.
        # TODO(P1, debug): Why priority can still be None?
        return self.priority or "", 0 if self.transcript is None else -len(
            str(self.transcript)
        )
