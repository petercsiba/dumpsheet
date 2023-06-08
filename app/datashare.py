import datetime
import json
import time

from dataclasses import dataclass, field, is_dataclass, asdict, fields
from json import JSONEncoder
from typing import Any, Dict, List, Optional, Type


def check_required_str(name, s):
    if s is None or len(s) == 0:
        print(f"ERROR: DataEntry invalid string {name}: {s}")


def check_required_list(name, lst):
    if lst is None or len(lst) == 0:
        print(f"ERROR: DataEntry invalid list {name}: {lst}")


class DateTimeEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()

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
                # If parsing failed, leave the value as it is
                pass
    return dict_


def dataclass_to_json(dataclass_obj: dataclass):
    # Convert the data_entry object to a dictionary, and then json.dumps
    # the complex objects to store them as strings in DynamoDB.
    item_dict = asdict(dataclass_obj)
    return json.dumps(item_dict, cls=DateTimeEncoder)


def dict_to_dataclass(dict_, data_class_type: Type[Any]) -> dataclass:
    init_values = {}
    for f in fields(data_class_type):
        if is_dataclass(f.type):
            init_values[f.name] = dict_to_dataclass(dict_[f.name], f.type)
        else:
            init_values[f.name] = dict_[f.name]
    return data_class_type(**init_values)


def json_to_dataclass(json_data, data_class_type: Type[Any]) -> dataclass:
    dict_ = json.loads(json_data, object_hook=datetime_decoder)
    return dict_to_dataclass(dict_, data_class_type)


@dataclass
class EmailParams:
    sender: str
    # To keep things simple, we only support one recipient for now (although adding more is simple)
    recipient: str
    recipient_full_name: str
    subject: str
    body_text: str = None
    body_html: str = None
    reply_to: list[str] = None
    bcc: list[str] = None
    attachment_paths: list = None

    def get_recipient_first_name(self):
        return self.recipient_full_name.split()[0]


# TODO(P1): One day we will need to support merging to one canonical key.
@dataclass
class PersonKey:
    user_id: str
    name: str


@dataclass
# These are pre-merged snapshots of a person
class PersonDataEntry:
    # Main identifier
    name: str = None

    # INPUTS
    # All text mentioning them joined into one string
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
    # intent => draft (ideally would be a sub-dataclass, but it's a bit tough to deal with nested ones.
    drafts: List[Dict[str, str]] = field(default_factory=list)

    parsing_error: str = None

    # Katka really wants text priorities
    PRIORITIES_MAPPING = {
        5: "P0 - DO IT ASAP!",
        4: "P1 - High: This is important & needed",
        3: "P2 - Medium: Nice to have",
        2: "P3 - Unsure: Check if you have time",
        1: "P4 - Low: Just don't bother",
    }


@dataclass
class User:
    # Partition Key
    user_id: str
    # user_id maps one-to-one to email_address
    email_address: str
    full_name: str

    @staticmethod
    def generate_user_id():
        return f"user{time.time()}"


@dataclass
class DataEntryKey:
    user_id: str
    event_name: str


@dataclass
class DataEntry:
    # Partition Key, Sort Key
    user_id: str
    event_name: str  # used as human identifier, e.g. date, location, actual event name
    # Additional items
    event_id: str  # used as computer idempotency key, e.g. received email Message-id
    event_timestamp: datetime.datetime
    email_reply_params: EmailParams
    input_s3_url: Optional[str] = None  # No S3 for local testing
    input_transcripts: List[str] = field(default_factory=list)
    # Note: these are pre-merged before serializing into the People table
    output_people_snapshot: List[PersonDataEntry] = field(default_factory=list)
    output_webpage_url: str = None

    def double_check_inputs(self):
        check_required_str("user_id", self.user_id)
        check_required_str("event_name", self.event_name)
        check_required_list("input_transcripts", self.input_transcripts)
