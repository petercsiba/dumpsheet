from enum import Enum

from gpt_form_filler.form import FieldDefinition, FormDefinition, Option


class FormName(Enum):
    CONTACTS = "contacts"
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


def get_form(form_name: FormName) -> FormDefinition:
    if form_name == FormName.CONTACTS:
        return FormDefinition(FormName.CONTACTS.value, CONTACTS_FIELDS)
    if form_name == FormName.FOOD_LOG:
        return FormDefinition(FormName.FOOD_LOG.value, FOOD_LOG_FIELDS)
    raise ValueError(f"unknown form_name: {form_name.value}")


CONTACTS_FIELDS = [
    FieldDefinition(
        name="recording_time",
        field_type="date",
        label="Recorded Time",
        description="Which date the recording took place",
        ignore_in_prompt=True,  # Will be filled in manually
        ignore_in_email=True,
    ),
    FieldDefinition(
        name="is_inputs_checked",
        field_type="bool",
        label="Checked Outputs",
        description="Whether the user checked the correctness of the Voxana output",
        ignore_in_prompt=True,
        default_value=False,
        ignore_in_email=True,
    ),
    FieldDefinition(
        name="is_done",
        field_type="bool",
        label="Done",
        description="Whether the user did finalize the follow up",
        ignore_in_prompt=True,
        default_value=False,
        ignore_in_email=True,
    ),
    FieldDefinition(
        name="name",
        field_type="text",
        label="Name",
        description="Name of the person I talked with",
        ignore_in_prompt=True,  # Will be filled in manually
    ),
    FieldDefinition(
        name="role",
        field_type="text",
        label="Role",
        description="Current role or latest job experience",
    ),
    FieldDefinition(
        name="industry",
        field_type="text",
        label="Industry",
        description=(
            "which business industry area they specialize in professionally, "
            "e.g. construction, tech, fintech, business, consulting, marketing"
        ),
    ),
    FieldDefinition(
        name="their_needs",
        field_type="text",
        label="Their Needs",
        description="list of what the person is looking for, null for empty",
    ),
    FieldDefinition(
        # TODO(P1, devx): We might want add list form type here.
        name="my_action_items",
        field_type="text",
        label="My Action Items",
        description=(
            "list of action items I explicitly assigned myself to address after the meeting, null for empty"
        ),
    ),
    FieldDefinition(
        name="suggested_revisit",
        field_type="select",
        label="Suggested Priority",
        description=("priority of when should i respond to the person"),
        options=[
            Option(label="HIGH: Take Action Today!", value="P0"),
            Option(label="MEDIUM: Make Sure To Stay In Touch", value="P1"),
            Option(label="LOW: potentially revisit in the future", value="P2"),
        ],
        default_value="P2",
    ),
    FieldDefinition(
        name="key_facts",
        field_type="text",
        label="Key Facts",
        description="list of key facts each fact in a super-short up to 5 word brief, null for empty",
    ),
    FieldDefinition(
        name="response_message_type",
        field_type="select",
        label="Response Message Channel",
        description=(
            "best message channel to keep the conversation going, either it is mentioned in the text, "
            "and if not, then assume from how friendly / professional the chat was"
        ),
        options=[
            Option(label="Email", value="email"),
            Option(label="LinkedIn", value="linkedin"),
            Option(label="WhatsApp", value="whatsapp"),
            Option(label="Text", value="sms"),
        ],
        default_value="sms",
        ignore_in_display=True,
    ),
    FieldDefinition(
        name="suggested_response_item",
        field_type="text",
        label="Suggested Response Item",
        description=(
            "one key topic or item for my follow up response to the person, "
            "default to 'great to meet you, let me know if I can ever do anything for you'"
        ),
        ignore_in_display=True,  # This field is only used as a hint for draft generation.
    ),
    FieldDefinition(
        name="next_draft",
        field_type="text",
        label="Drafted Follow Up",
        description="casual yet professional short to the point draft for my action from suggested_response_item",
        ignore_in_prompt=True,  # We only fill this in with separate GPT prompt when the transcript is long enough
        ignore_in_email=True,  # Manually hacked up into a separate display component
    ),
    FieldDefinition(
        name="summarized_note",
        field_type="text",
        label="Detailed Notes",
        description="short concise structured summary of the meeting note",
        ignore_in_prompt=True,  # We only fill this in with separate GPT prompt when the transcript is long enough
        ignore_in_email=True,  # Manually hacked up into a separate display component
    ),
]


FOOD_LOG_FIELDS = [
    FieldDefinition(
        name="recording_time",
        field_type="date",
        label="Recording Time",
        description="Date time of the log entry",
    ),
    FieldDefinition(
        name="ingredient",
        field_type="text",
        label="Ingredient",
        description="one food item like you would see on an ingredients list",
    ),
    FieldDefinition(
        name="amount",
        field_type="text",
        label="Amount",
        description=(
            "approximate amount of the ingredient taken, if not specified it can be just using 'a bit' or 'some"
        ),
    ),
    FieldDefinition(
        name="activity",
        field_type="text",
        label="Activity",
        description="which business area they specialize in professionally",
    ),
]
