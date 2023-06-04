import datetime
from dataclasses import dataclass, field
from typing import List, Optional


def check_required_str(name, s):
    if s is None or len(s) == 0:
        print(f"ERROR: DataEntry invalid {name}: {s}")


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


@dataclass
class Person:
    user_id: str
    name: str
    person_id: str
    vibes: str
    role: str
    priority: int
    transcript: str
    # These are follow_ups mentioned in any transcript
    follow_ups: List[str] = field(default_factory=list)
    drafts: List[str] = field(default_factory=list)
    industry: Optional[str] = None
    needs: Optional[List[str]] = None

    def partition_key(self):
        return self.user_id

    def sort_key(self):
        return self.name


@dataclass
class User:
    # user_id maps one-to-one to email
    user_id: str
    email_address: str
    full_name: str

    def partition_key(self):
        return self.user_id

    def sort_key(self):
        return None


@dataclass
class DataEntry:
    user_id: str
    event_name: str
    event_timestamp: datetime.datetime
    email_reply_params: EmailParams
    input_s3_url: Optional[str] = None  # I guess for local testing, no S3
    input_transcripts: List[str] = field(default_factory=list)
    output_summaries: List[Person] = field(default_factory=list)
    output_drafts: List[dict] = field(default_factory=list)
    output_webpage_url: str = None

    def partition_key(self):
        return self.user_id

    def sort_key(self):
        return self.event_name

    def double_check_inputs(self):
        check_required_str("user_id", self.user_id)
        check_required_str("event_name", self.event_name)
