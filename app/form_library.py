from app.form import FieldDefinition, FormDefinition, FormName, Option


def get_form(form_name: FormName) -> FormDefinition:
    if form_name == FormName.CONTACTS:
        return FormDefinition(FormName.CONTACTS, CONTACTS_FIELDS)
    if form_name == FormName.FOOD_LOG:
        return FormDefinition(FormName.FOOD_LOG, FOOD_LOG_FIELDS)
    if form_name == FormName.HUBSPOT_CONTACT:
        return FormDefinition(FormName.HUBSPOT_CONTACT, HUBSPOT_CONTACT_FIELDS)
    if form_name == FormName.HUBSPOT_MEETING:
        return FormDefinition(FormName.HUBSPOT_MEETING, HUBSPOT_CALL_FIELDS)
    if form_name == FormName.HUBSPOT_TASK:
        return FormDefinition(FormName.HUBSPOT_TASK, HUBSPOT_TASK_FIELDS)
    raise ValueError(f"unknown form_name: {form_name.value}")


CONTACTS_FIELDS = [
    FieldDefinition(
        name="recording_time",
        field_type="date",
        label="Recorded Time",
        description="Which date the recording took place",
        ignore_in_prompt=True,  # Will be filled in manually
    ),
    FieldDefinition(
        name="is_inputs_checked",
        field_type="bool",
        label="Checked inputs?",
        description="Whether the user checked the correctness of the Voxana output",
        ignore_in_prompt=True,
        default_value=False,
    ),
    FieldDefinition(
        name="is_done",
        field_type="bool",
        label="Done?",
        description="Whether the user did finalize the follow up",
        ignore_in_prompt=True,
        default_value=False,
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
        name="key_facts",
        field_type="text",
        label="Key Facts",
        description="list of key facts each fact in a super-short up to 5 word brief, null for empty",
    ),
    FieldDefinition(
        name="suggested_revisit",
        field_type="select",
        label="Suggested Revisit",
        description=(
            "priority of when should i respond to them, PO (today), P1 (end of week), P2 (later)"
        ),
        options=[
            Option(label="P0 (today)", value="P0"),
            Option(label="P1 (end of week)", value="P1"),
            Option(label="P2 (later)", value="P2"),
        ],
        default_value="P2",
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
    ),
    FieldDefinition(
        name="summarized_note",
        field_type="text",
        label="Summarized Note",
        description="short concise structured summary of the meeting note",
        ignore_in_prompt=True,  # We only fill this in with separate GPT prompt when the transcript is long enough
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


HUBSPOT_CONTACT_FIELDS = [
    FieldDefinition(
        name="hubspot_owner_id",
        field_type="number",
        label="Contact owner",
        description=(
            "The owner of a contact. This can be any HubSpot user or Salesforce integration user, "
            "and can be set manually or via Workflows."
        ),
        options=[],
        ignore_in_prompt=True,
        ignore_in_display=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="firstname",
        field_type="text",
        label="First Name",
        description="Contacts first name (not surname)",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="lastname",
        field_type="text",
        label="Last Name",
        description="Contacts last name (not given name)",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="jobtitle",
        field_type="text",
        label="Job Title",
        description="A contact's job title",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="company",
        field_type="text",
        label="Company Name",
        description=(
            "Name of the contact's company. This can be set independently from the name property on "
            "the contact's associated company."
        ),
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="industry",
        field_type="text",
        label="Industry",
        description="The Industry a contact is in",
        options=[],
        custom_field=False,
    ),
    # NOTE: Unclear what are the rules to decide
    # FieldDefinition(
    #     name="lifecyclestage",
    #     field_type="radio",
    #     label="Lifecycle Stage",
    #     description="The qualification of contacts to sales readiness.",
    #     options=[
    #         Option(label="Subscriber", value="subscriber"),
    #         Option(label="Lead", value="lead"),
    #         Option(label="Marketing Qualified Lead", value="marketingqualifiedlead"),
    #         Option(label="Sales Qualified Lead", value="salesqualifiedlead"),
    #         Option(label="Opportunity", value="opportunity"),
    #         Option(label="Customer", value="customer"),
    #         Option(label="Evangelist", value="evangelist"),
    #         Option(label="Other", value="other"),
    #     ],
    #     group_name="contactinformation",
    #     custom_field=False,
    # ),
    # NOTE: Unclear what are the rules to assign
    # FieldDefinition(
    #     name="hs_lead_status",
    #     field_type="radio",
    #     label="Lead Status",
    #     description="The contact's sales, prospecting or outreach status",
    #     options=[
    #         Option(label="New", value="NEW"),
    #         Option(label="Open", value="OPEN"),
    #         Option(label="In Progress", value="IN_PROGRESS"),
    #         Option(label="Open Deal", value="OPEN_DEAL"),
    #         Option(label="Unqualified", value="UNQUALIFIED"),
    #         Option(label="Attempted to Contact", value="ATTEMPTED_TO_CONTACT"),
    #         Option(label="Connected", value="CONNECTED"),
    #         Option(label="Bad Timing", value="BAD_TIMING"),
    #     ],
    #     group_name="sales_properties",
    #     custom_field=False,
    # ),
    FieldDefinition(
        name="email",
        field_type="text",
        label="Email",
        description="A contact's email address",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="phone",
        field_type="phonenumber",
        label="Phone Number",
        description="A contact's primary phone number",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="city",
        field_type="text",
        label="City",
        description="A contact's city of residence",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="state",
        field_type="text",
        label="State/Region",
        description="The contact's state of residence.",
        options=[],
        ignore_in_display=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="country",
        field_type="text",
        label="Country/Region",
        description="The contact's country/region of residence.",
        options=[],
        ignore_in_display=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        ignore_in_prompt=True,
        custom_field=False,
    ),
]

HUBSPOT_CALL_FIELDS = [
    # "hs_activity_type": FieldDefinition(
    #     name="hs_activity_type",
    #     field_type="select",
    #     label="Call and meeting type",
    #     description="The activity type of the engagement",
    #     options=[],
    #     group_name="engagement",
    #     hubspot_defined=True,
    # ),
    FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        ignore_in_prompt=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="hubspot_owner_id",
        field_type="number",
        label="Activity assigned to",
        description=(
            "The user that the activity is assigned to in HubSpot. "
            "This can be any HubSpot user or Salesforce integration user, and can be set manually or via Workflows."
        ),
        options=[],
        ignore_in_prompt=True,
        ignore_in_display=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_callee_object_id",
        field_type="number",
        label="Callee object id",
        description=(
            "The ID of the HubSpot record associated with the call. "
            "This will be the recipient of the call for OUTBOUND calls, or the dialer of the call for INBOUND calls."
        ),
        options=[],
        ignore_in_prompt=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_direction",
        field_type="select",
        label="Call direction",
        description="The direction of the call from the perspective of the HubSpot user.",
        options=[
            Option(label="Inbound", value="INBOUND"),
            Option(label="Outbound", value="OUTBOUND"),
        ],
        custom_field=False,
    ),
    # TODO(P1, fullness): Seems ignored by GPT
    FieldDefinition(
        name="hs_call_disposition",
        field_type="select",
        label="Call outcome",
        description="The outcome of the call",
        options=[
            Option(label="Busy", value="9d9162e7-6cf3-4944-bf63-4dff82258764"),
            Option(label="Connected", value="f240bbac-87c9-4f6e-bf70-924b57d47db"),
            Option(
                label="Left live message", value="a4c4c377-d246-4b32-a13b-75a56a4cd0ff"
            ),
            Option(
                label="Left voicemail", value="b2cf5968-551e-4856-9783-52b3da59a7d0"
            ),
            Option(label="No answer", value="73a0d17f-1163-4015-bdd5-ec830791da20"),
            Option(label="Wrong number", value="17b47fee-58de-441e-a44c-c6300d46f273"),
        ],
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_from_number",
        field_type="text",
        label="From number",
        description="The phone number of the person that initiated the call",
        options=[],
        ignore_in_prompt=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_status",
        field_type="select",
        label="Call status",
        description="The status of the call",
        options=[
            Option(label="Busy", value="BUSY"),
            Option(label="Calling CRM User", value="CALLING_CRM_USER"),
            Option(label="Canceled", value="CANCELED"),
            Option(label="Completed", value="COMPLETED"),
            Option(label="Connecting", value="CONNECTING"),
            Option(label="Failed", value="FAILED"),
            Option(label="In Progress", value="IN_PROGRESS"),
            Option(label="Missed", value="MISSED"),
            Option(label="No Answer", value="NO_ANSWER"),
            Option(label="Queued", value="QUEUED"),
            Option(label="Ringing", value="RINGING"),
        ],
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_title",
        field_type="text",
        label="Call Title",
        description="The title of the call",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_to_number",
        field_type="text",
        label="To Number",
        description="The phone number of the person that was called",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_timestamp",
        field_type="date",
        label="Activity date",
        description="The date that an engagement occurred",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_call_body",
        field_type="html",
        label="Call notes",
        description="""
        A concise structured summary of the entire transcript,
        make sure to include all facts, if needed label those facts
        so I can review this in a year and know what happened.
        For better readability, use html paragraphs and bullet points.
        """,
        options=[],
        custom_field=False,
    ),
]

# https://community.hubspot.com/t5/APIs-Integrations/Create-TASK-engagement-with-due-date-and-reminder-via-API/m-p/235759#M14655
HUBSPOT_TASK_FIELDS = [
    FieldDefinition(
        name="hs_object_id",
        field_type="number",
        label="Record ID",
        description=(
            "The unique ID for this record. This value is automatically set by HubSpot and may not be modified."
        ),
        options=[],
        ignore_in_prompt=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="hubspot_owner_id",
        field_type="number",
        label="Assigned to",
        description=(
            "The user that the task is assigned to in HubSpot. "
            "This can be any HubSpot user or Salesforce integration user, and can be set manually or via Workflows."
        ),
        options=[],
        ignore_in_prompt=True,
        ignore_in_display=True,
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_task_subject",
        field_type="text",
        label="Task Title",
        description="The title of the task",
        options=[],
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_task_priority",
        field_type="select",
        label="Priority",
        description="The priority of the task",
        options=[
            Option(label="None", value="NONE"),
            Option(label="Low", value="LOW"),
            Option(label="Medium", value="MEDIUM"),
            Option(label="High", value="HIGH"),
        ],
        custom_field=False,
    ),
    FieldDefinition(
        name="hs_timestamp",
        field_type="date",
        label="Due date",
        description="The due date of the task",
        options=[],
        custom_field=False,
    ),
    # NOTE: The user should set this
    # FieldDefinition(
    #     name="hs_task_status",
    #     field_type="select",
    #     label="Task Status",
    #     description="The status of the task",
    #     options=[
    #         Option(label="Completed", value="COMPLETED"),
    #         Option(label="Deferred", value="DEFERRED"),
    #         Option(label="In Progress", value="IN_PROGRESS"),
    #         Option(label="Not Started", value="NOT_STARTED"),
    #         Option(label="Waiting", value="WAITING"),
    #     ],
    #     group_name="task",
    #     custom_field=False,
    # ),
    # NOTE: Unclear how is this derived
    # FieldDefinition(
    #     name="hs_task_type",
    #     field_type="select",
    #     label="Task Type",
    #     description="The type of the task",
    #     options=[
    #         Option(label="Call", value="CALL"),
    #         Option(label="Email", value="EMAIL"),
    #         Option(label="LinkedIn", value="LINKED_IN"),
    #         Option(label="Meeting", value="MEETING"),
    #         Option(
    #             label="Sales Navigator - Connection Request", value="LINKED_IN_CONNECT"
    #         ),
    #         Option(label="Sales Navigator - InMail", value="LINKED_IN_MESSAGE"),
    #         Option(label="To Do", value="TODO"),
    #     ],
    #     group_name="task",
    #     custom_field=False,
    # ),
    FieldDefinition(
        name="hs_task_body",
        field_type="html",
        label="To Dos",
        description="Action items and follows ups I need to do in concise bullet points ordered by priority top down",
        options=[],
        ignore_in_display=True,  # It's displayed as a separate textarea
        custom_field=False,
    ),
]
