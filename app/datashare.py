import datetime
from dataclasses import dataclass, field
from typing import List, Optional

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
    input_s3_url: str
    input_transcript: str
    output_summaries: List[Person] = field(default_factory=list)
    output_drafts: List[dict] = field(default_factory=list)
    output_webpage_url: str = None

    def partition_key(self):
        return self.user_id

    def sort_key(self):
        return self.event_name


