# TODO(P0, ux): Make the emails more funny!
# TODO(P2, ux): Setup Supabase SMTP to use the for login stuff as other (Amazon SES)
#  SMTP Settings: You can use your own SMTP server instead of the built-in email service.
#  https://app.supabase.com/project/kubtuncgxkefdlzdnnue/settings/auth
import os
import re
import time
import traceback
import uuid
from email.header import decode_header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import List, Optional
from uuid import UUID

import boto3

from app.datashare import PersonDataEntry
from app.email_template import (
    button_snippet_for_spreadsheet,
    full_template,
    main_content_template,
    simple_email_body_html,
    table_row_template,
    table_template,
)
from app.hubspot_dump import HubspotDataEntry
from app.hubspot_models import FieldNames, HubspotObject
from common.aws_utils import is_running_in_aws
from common.config import (
    DEBUG_RECIPIENTS,
    NO_REPLY_EMAIL,
    SENDER_EMAIL,
    SENDER_EMAIL_ALERTS,
    SKIP_SENDING_EMAILS,
    SUPPORT_EMAIL,
)
from common.form import FormData
from common.storage_utils import pretty_filesize_path
from common.twillio_client import TwilioClient
from database.account import Account
from database.email_log import EmailLog
from database.models import BaseDataEntry


def sanitize_filename(filename: str) -> str:
    # Replace spaces with underscores
    filename = filename.replace(" ", "_")

    # Remove invalid characters
    filename = re.sub(r"[^\w_.-]", "", filename)

    # Avoid using leading period
    if filename and filename[0] == ".":
        filename = filename[1:]
    return filename


def store_and_get_attachments_from_email(msg, file_name_prefix: str):
    # Process the attachments
    attachment_file_paths = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue

        # Get the attachment's filename
        orig_file_name = part.get_filename()
        print(f"Parsing attachment {orig_file_name}")

        if not bool(orig_file_name):
            continue

        # If there is an attachment, save it to a file
        file_name = sanitize_filename(f"{file_name_prefix}-{orig_file_name}")
        file_path = os.path.join("/tmp/", file_name)
        with open(file_path, "wb") as f:
            f.write(part.get_payload(decode=True))

        attachment_file_paths.append(file_path)

    print(
        f"store_and_get_attachments_from_email got {len(attachment_file_paths)} total attachments"
    )
    return attachment_file_paths


# TODO(P1, test this)
def decode_str(s):
    """Decode the specified RFC 2047 string."""
    # Came up with Marting Stuebler represented as =?UTF-8?Q?Martin_St=C3=BCbler?=!
    parts = decode_header(s)
    decoded_parts = []
    for part, encoding in parts:
        if encoding:
            decoded_parts.append(part.decode(encoding))
        elif isinstance(part, bytes):
            # bytes in us-ascii encoding
            decoded_parts.append(part.decode("us-ascii"))
        else:
            # already str in us-ascii encoding
            decoded_parts.append(part)
    return " ".join(decoded_parts)


def get_email_params_for_reply(msg):
    # The variable naming is a bit confusing here, as `msg` refers to received email,
    # while all the returned Email params are for the reply (i.e. recipient = reply_to)
    email_from = msg.get("From")
    orig_to_address = msg.get("To")
    orig_subject = msg.get("Subject")
    # Parse the address
    sender_full_name, sender_email_addr = parseaddr(email_from)
    sender_full_name = (
        "Person" if sender_full_name is None else decode_str(sender_full_name)
    )
    reply_to_address = msg.get("Reply-To")
    if reply_to_address is None or not isinstance(reply_to_address, str):
        print("No reply-to address provided, falling back to from_address")
        reply_to_address = sender_email_addr
    print(
        f"email from {sender_full_name} ({sender_email_addr}) reply-to {reply_to_address} "
        f"orig_to_address {orig_to_address}, orig_subject {orig_subject}"
    )
    return EmailLog(
        sender=orig_to_address,
        recipient=reply_to_address,
        recipient_full_name=sender_full_name,
        subject=f"Re: {orig_subject}",
        reply_to=SUPPORT_EMAIL,  # We skip the orig_to_address, as that would trigger another transcription.
    )


def create_raw_email_with_attachments(params: EmailLog):
    if not isinstance(params.recipient, str):
        print(
            f"email_address is NOT a string {params.recipient}, falling back to {DEBUG_RECIPIENTS}"
        )
        params.recipient = DEBUG_RECIPIENTS[0]
    # Fill in sender name
    sender_name, sender_email = parseaddr(params.sender)
    if sender_name == "":
        params.sender = SENDER_EMAIL

    if params.reply_to is None:
        params.reply_to = [params.sender]
    if params.attachment_paths is None:
        params.attachment_paths = []

    # I mean the params expect a list, but this is python and developers move fast.
    if not isinstance(params.reply_to, list):
        params.reply_to = [str(params.reply_to)]

    if params.bcc is not None:
        if not isinstance(params.bcc, list):
            params.bcc = [str(params.bcc)]
        # Filter out the recipient from the bcc list
        params.bcc = list(set(params.bcc) - {params.recipient})

    # TODO(P2): Ideally we should support both text and html formats in the same email (this is possible)
    if params.body_html is None:
        if params.body_text is None:
            print("ERROR: One of body_html or body_text has to be set!")
        params.body_html = (
            """<html>
            <head></head>
            <body>
              """
            + params.body_text
            + """
        </body>
        </html>
        """
        )

    # Create a multipart/mixed parent container
    msg = MIMEMultipart("mixed")
    msg["Subject"] = params.subject
    msg["From"] = params.sender
    msg["To"] = params.recipient
    msg["Reply-To"] = ", ".join(params.reply_to)
    if params.bcc is not None:
        msg["Bcc"] = ", ".join(params.bcc)

    print(
        f"Sending email from {msg['From']} to {msg['To']} (and bcc {msg['Bcc']}) with subject {msg['Subject']}"
    )

    # Create a multipart/alternative child container
    msg_body = MIMEMultipart("alternative")

    # Encode the text and add it to the child container
    msg_body.attach(MIMEText(params.body_html, "html"))

    # Attach the multipart/alternative child container to the multipart/mixed parent container
    msg.attach(msg_body)

    # Add attachments
    for attachment_path in params.attachment_paths:
        with open(attachment_path, "rb") as file:
            attachment = MIMEApplication(file.read())
        # Define the content ID
        attachment.add_header(
            "Content-Disposition", "attachment", filename=attachment_path.split("/")[-1]
        )
        # Add the attachment to the parent container
        msg.attach(attachment)

    return msg


# TODO(P2): Gmail marks us as spam - no clear way around it. Some easy-ish ways:
#     * [DONE] Use the same email sender address
#     * [DONE] Authenticate emails DKIM, DMARC, SPF
#     * Next(Mehdi): "Prime" your domain, blast emails, make everyone to open it (this will happen over time).
#     * Add Unsubscribe button
#     * Opt-in process (verify email)
#     * Over-time, the higher the engagement with our emails the better.
def send_email(params: EmailLog) -> bool:
    params.bcc = DEBUG_RECIPIENTS
    raw_email = create_raw_email_with_attachments(params)

    if not is_running_in_aws() or str(SKIP_SENDING_EMAILS) == "1":
        # TODO(P2, testing): Ideally we should also test the translation from params to raw email.
        print(
            f"Skipping ses.send_raw_email cause NOT in AWS or SKIP_SENDING_EMAILS={SKIP_SENDING_EMAILS} "
            f"Dumping the email {params.idempotency_id} contents {params}"
        )
        if not params.check_if_already_sent():
            # TODO(P1, devx): Ideally, this would update the row, currently fails on the unique constraint.
            params.log_email()  # to test db queries too
        return True

    if params.check_if_already_sent():
        # TODO(P2, bug): params.account might be None, observe for now as it might be a result of an inconsistent state.
        print(
            f"SKIPPING email '{params.idempotency_id}' cause already sent for {params.account}"
        )
        return True
    try:
        print(
            f"Attempting to send email {params.idempotency_id} to {params.recipient} "
            f"with attached files {params.attachment_paths}"
        )

        ses = boto3.client("ses")
        response = ses.send_raw_email(
            Source=params.sender,
            # TIL, list(str) returns characters, instead of having a single entry list [str]
            Destinations=[params.recipient] + params.bcc,
            RawMessage={
                "Data": raw_email.as_string(),
            },
            # TODO(P1, cx): We need DB for this too, as MessageDeduplicationId is for SQS (and this is SES).
            #   check_message_id_in_database, store_message_id_in_database (anyway would be nice to store all msgs)
            # MessageDeduplicationId=dedup_id,
        )

        message_id = response["MessageId"]
        print(f"Email sent! Message ID: {message_id}, Subject: {params.subject}")

        params.log_email()
        return True
    except Exception as e:
        print(f"Email with subject {params.subject} failed to send. {e}")
        traceback.print_exc()
        return False


# E.g. "2023-10-05_193824-0500-James_white_for_testing.m4a" -> James White For Testing
# or 2023-10-06_210315-0500-Andrej_Jursa_Vestberry.m4a.mp4
def _make_human_readable(filename):
    match = re.search(r"\d{4}-\d{2}-\d{2}_\d{6}-\d{4}-([\w_\-]+)(?=\.\w+)", filename)
    if match:
        name_part = match.group(1)
        name_part = name_part.replace("_", " ")
        return " ".join(word.capitalize() for word in name_part.split(" "))
    else:
        print(f"WARNING: could not find words in filename {filename}")
        return ""


def _confirmation_success_next_steps(first_time_use: bool) -> str:
    if first_time_use:
        return """
            <p style="line-height: 1.5;">I received the voice recording and now it’s my turn to get to work.</p>
            <p style="line-height: 1.5;">Within a few minutes you should receive 2 emails from me: </p>
            <p style="line-height: 1.5; margin-left: 20px"><span style="font-weight: bold;">#1</span>
                with a <b>link to a Google Sheet</b> which I will start for you to help
                you keep all your networking information organized
            </p>
            <p style="line-height: 1.5; margin-left: 20px"><span style="font-weight: bold;">#2</span>
                    with a <b>draft of the follow-up message</b> based on what you shared with me
                    + a <b>structured recap</b> of what you were talking about
            </p>
        """
    else:
        return """
            <p style="line-height: 1.5;">I received your voice recording and I am crunching through it! <br />
            <br />
            As per usual, within a few minutes I’ll be sending you an email with:
            <ul>
                <li style="margin-bottom: 8px">a <b>draft of the follow-up message</b> based on what you shared</li>
                <li style="margin-bottom: 8px">a <b>structured recap</b> of what you were talking about</li>
                <li style="margin-bottom: 8px">a <b>link to your updated Google Sheet</b>
                    where all your networking notes are neatly organized
                </li>
            </ul>
            </p>
        """


# TODO(P1): Move email templates to separate files - ideally using a standardized template language like handlebars.
#   * Yeah, we might want to centralize this into Hubspot Transactional email API.
# We have attachment_paths separate, so the response email doesn't re-attach them.
def send_confirmation(params: EmailLog, first_time_use: bool, attachment_paths):
    first_name = params.get_recipient_first_name()
    if len(attachment_paths) == 0:
        params.idempotency_id = f"{params.idempotency_id}-forgot-attachment"
        params.subject = "We have received your message - but no recording was found"
        params.body_html = simple_email_body_html(
            title=params.subject,
            content_text="""
            <p>Yo {}, did you forgot to attach your voice memo in your email?
            ☕ I would love to brew you a coffee, but I ain't real, so an emoji will have to do it: ☕</p>
            <p>Remember, any audio file would do, I can convert from any known audio file by myself!</p>
            """.format(
                first_name
            ),
        )
        send_email(params=params)
    else:
        file_list = []
        recording_name = ""
        for file_path in attachment_paths:
            file_size = pretty_filesize_path(file_path)
            filename = os.path.basename(file_path)
            recording_name = _make_human_readable(filename)
            print(
                f"DEBUG: filename {filename} converted to display name {recording_name}"
            )
            if len(recording_name) < 4:
                recording_name = ""
            file_list.append(
                f"""<li style="margin-bottom: 8px">{filename} ({file_size})</li>"""
            )
        file_list_str = "\n".join(file_list)

        params.idempotency_id = f"{params.idempotency_id}-confirmation"
        if first_time_use:
            params.subject = "Congrats - I just received your first voice recording!"
        else:
            params.subject = (
                f"Confirmation - we have received your recording {recording_name}"
            )

        params.body_html = simple_email_body_html(
            title=params.subject,
            content_text="""
            <p>Hi {}, </p>
            {confirmation_success_html}
            <p>I've received the following files:</p>
            <p><ul>{file_list_str}</ul></p>
            <p>Talk soon! <br /><br /> Voxana</p>""".format(
                first_name,
                confirmation_success_html=_confirmation_success_next_steps(
                    first_time_use=first_time_use
                ),
                file_list_str=file_list_str,
            ),
        )
        send_email(params=params)


def send_app_upload_confirmation(params: EmailLog, first_time_use: bool):
    params.idempotency_id = f"{params.idempotency_id}-confirmation"
    if first_time_use:
        params.subject = "Congrats - I just received your first voice recording!"
    else:
        params.subject = "Confirmation - I have received your voice recording upload"
    params.body_html = simple_email_body_html(
        title=params.subject,
        content_text="""
        <p>Hi boss, </p>
        {confirmation_success_html}
        <p>Talk soon! <br /><br /> Voxana</p>
        """.format(
            confirmation_success_html=_confirmation_success_next_steps(first_time_use)
        ),
    )
    send_email(params=params)


def _format_summary_table_row(label: str, value: str) -> str:
    # if len(str(value)) <= 1:
    #    return None

    if value is None:
        display_value = "None"
    elif isinstance(value, str):
        # TODO(P1, ux): We could better format str lists, e.g when ChatGPT outputs type:str of
        # 1. Personal Details: Katka is from Slovakia and has an MBA from Columbia.
        # 2. Professional Interests: She is involved in building AI voice assistants.
        # we could split by new line and see that 1., 2., ... etc.
        display_value = value.replace("\n", "\n<br />")
    elif isinstance(value, list):
        li_items = "".join(
            f"""<li style="margin-bottom: 8px">{item}</li>""" for item in value
        )
        display_value = f"<ul>{li_items}</ul>"
    elif isinstance(value, dict):
        li_items = "".join(
            f"""<li style="margin-bottom: 8px"><strong>{item_key}</strong>: {item_value}</li>"""
            for item_key, item_value in value.items()
        )
        display_value = f"<ul>{li_items}</ul>"
    else:
        print(
            f"WARNING: Unhandled display value for label {label} ({type(value)}): {value}"
        )
        display_value = str(value)

    return table_row_template.format(
        label=label,
        value=display_value,
    )


def _form_data_to_email_table_html(form_data: FormData) -> str:
    rows = []
    for field in form_data.form.fields:
        if field.ignore_in_display or field.ignore_in_email:
            print(
                f"INFO: ignoring {field.name} for emails (ignore_id_display: {field.ignore_in_display}"
                f"ignore_in_email: {field.ignore_in_email}"
            )
            continue
        rows.append(
            _format_summary_table_row(
                field.label, value=form_data.get_display_value(field.name)
            )
        )
    return "\n".join(rows)


def _hubspot_obj_to_table(
    heading: str,
    obj: Optional[HubspotObject],
    extra_content: str = "",
) -> str:
    rows = []
    for field in obj.form.fields:
        if field.ignore_in_display or field.ignore_in_email:
            print(
                f"INFO: ignoring {field.name} for emails (ignore_id_display: {field.ignore_in_display}"
                f"ignore_in_email: {field.ignore_in_email}"
            )
            continue
        key, value = obj.get_field_display_label_with_value(field.name)
        rows.append(_format_summary_table_row(key, value))
    rows_html = "\n".join(rows)
    return table_template(
        heading=heading, rows_html=rows_html, extra_content_html=extra_content
    )


def _hubspot_objs_maybe_to_table(
    heading: str,
    obj: Optional[HubspotObject],
    gpt_obj: Optional[HubspotObject],
    extra_content: str = "",
) -> str:
    if obj is None:
        result = main_content_template(
            heading=heading, content="Could not sync data to HubSpot (API error)"
        )
        if gpt_obj is None:
            result = main_content_template(
                heading=heading,
                content="Could not parse data into structure (GPT error)",
            )
        else:
            result += _hubspot_obj_to_table(heading, gpt_obj, extra_content)
    else:
        result = _hubspot_obj_to_table(heading, obj, extra_content)
    return result


def send_hubspot_result(
    account_id: UUID, idempotency_id_prefix: str, data: HubspotDataEntry
) -> bool:
    person_name = data.contact_name()
    idempotency_id_suffix = data.state

    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=account_id,
        idempotency_id=f"{idempotency_id_prefix}-result-{idempotency_id_suffix}",
        subject=f"HubSpot Data Entry for {person_name} - {data.state.capitalize()}",
    )
    pre_header = email_params.subject

    if data.state in ["short", "incomplete"]:
        email_params.body_html = simple_email_body_html(
            title=f"Note is {data.state} - please enter more information.",
            sub_title="This is how I understood it",
            content_text=data.transcript,
        )
        return send_email(params=email_params)

    extra_info_map = {
        "error_gpt": "I had problems transforming your note into a HubSpot structures",
        "error_hubspot_sync": "I encountered problems while syncing your data into your HubSpot",
        "warning_already_created": "Note: The contact already exists in your HubSpot",
    }
    extra_info = ""
    if data.state in extra_info_map:
        extra_info_content = extra_info_map[data.state]
        extra_info = main_content_template(
            heading="Sync Status",
            content=extra_info_content,
        )
        pre_header = extra_info_content

    # success / error with partial results
    contact_table = _hubspot_objs_maybe_to_table(
        "Contact Info", data.contact, data.gpt_contact
    )

    # Bit of a hack to restructure rendering of task To Dos
    todos_extra_content = ""
    if bool(data.task):
        todos_field_name = FieldNames.HS_TASK_BODY.value
        if todos_field_name in data.task.data:
            todos_extra_content = """
            <p><b>{heading}</b></p>
            <p>{content}</p>""".format(
                heading="To Dos", content=data.task.get_display_value(todos_field_name)
            )

    task_table = _hubspot_objs_maybe_to_table(
        "Follow up Tasks",
        data.task,
        data.gpt_task,
        todos_extra_content,
    )

    if bool(data.call):
        call_body_value = data.call.get_display_value(FieldNames.HS_CALL_BODY.value)
        further_details = main_content_template(
            heading="Further Details",
            content=f"""<p style = "line-height: 1.5;" >{call_body_value}</p>""",
        )
    else:
        further_details = main_content_template(
            heading="Further Details",
            content="<p>Could not sync data to HubSpot (API error)</p>",
        )

    email_params.body_html = full_template(
        title="HubSpot Data Entry Confirmation",
        pre_header=pre_header,
        content="""
            {contact_table}
            {task_table}
            {further_details}
            {extra_info}
            """.format(
            contact_table=contact_table,
            task_table=task_table,
            further_details=further_details,
            extra_info=extra_info,
        ),
    )
    return send_email(params=email_params)


def _craft_result_email_body(
    person: PersonDataEntry, shareable_link: Optional[str]
) -> (str, str):
    # TODO(P1, ux): Migrate to new email template
    next_draft_html = ""
    summarized_note_html = ""
    gsheets_button_html = (
        button_snippet_for_spreadsheet(shareable_link) if bool(shareable_link) else ""
    )

    should_takeaways = True
    subject_prefix = "Notes on "
    if person.should_draft():
        if person.next_draft is None:
            print(
                f"WARNING: Somehow should_draft is true and next_draft is None for {person.name}"
            )
        else:
            should_takeaways = False
            # template = "draft"
            # We used to have person.response_message_type to denote email/sms, removed so user can decide.
            subject_prefix = "Drafted message for"
            next_draft_html = main_content_template(
                heading="Drafted message",
                content=person.next_draft.replace("\n", "<br />"),
            )
            summarized_note_html = """
                <div style="font-weight: bold; margin-bottom: 5px;">
                    Detailed Notes
                </div>
                <p style="line-height: 1.5;">{summarized_note}</p>
                """.format(
                summarized_note=person.summarized_note.replace("\n", "<br />")
            )
    if should_takeaways:
        # template = "takeaways"
        subject_prefix = "Takeaways from"  # nothing to draft, just to research / act on

    # Join the list items into a single string
    if person.should_show_full_contact_card():
        contact_card_html = table_template(
            heading="Contact card for your records / CRM",
            rows_html=_form_data_to_email_table_html(person.form_data),
            extra_content_html=summarized_note_html + gsheets_button_html,
        )
    else:
        contact_card_html = main_content_template(
            heading=f"Not enough information for {person.name}",
            content=(
                f"<p>Please talk more about {person.name}, I have too little context to confidently summarize.</p>"
                f"""<p style="line-height: 1.5;">This is what I got {person.transcript}</p>"""
            ),
        )
    res_content_html = """
{next_draft_html}
{contact_card_html}
""".format(
        next_draft_html=next_draft_html,
        contact_card_html=contact_card_html,
        # TODO(P0, research): Add feedback mechanism by data-entry-id (good, ok, bad).
        #   * There is some learning curve, but it's useful to get sth.
    )
    return subject_prefix, res_content_html


def send_result(
    account_id: UUID, idempotency_id_prefix: str, person: PersonDataEntry
) -> bool:
    person_name_safe = re.sub(r"\W", "-", person.name).lower()
    acc: Account = Account.get_by_id(account_id)
    subject_prefix, content_html = _craft_result_email_body(
        person, shareable_link=acc.get_shareable_spreadsheet_link()
    )

    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=account_id,
        idempotency_id=f"{idempotency_id_prefix}-{person_name_safe}",
        subject=f"{subject_prefix} {person.name}",
    )
    email_params.body_html = full_template(
        pre_header=f"Contact and follow up information for {person.name}",
        title=email_params.subject,
        content=content_html,
    )

    return send_email(params=email_params)


def send_result_rest_of_the_crowd(
    account_id: UUID, idempotency_id_prefix: str, people: List[PersonDataEntry]
) -> bool:
    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=account_id,
        idempotency_id=f"{idempotency_id_prefix}-rest-of-the-crowd",
        subject=f"You also mentioned these {len(people)} folks",
    )
    rows = []
    for person in people:
        rows.append(_format_summary_table_row(person.name, person.transcript))

    content_text = """
    <p style="line-height: 1.5;">These folks you mentioned, but unfortunately I didn't get enough context
    from your note to confidently draft a response or summarize their profile. </p>
    <p>Remember, you can always fill me in with a new recording.</p>
    {table_html}
    """.format(
        table_html=table_template(
            heading="The people you mentioned too",
            rows_html="\n".join(rows),
            extra_content_html="",
        )
    )
    email_params.body_html = simple_email_body_html(
        title=email_params.subject,
        content_text=content_text,
    )

    return send_email(params=email_params)


def send_result_no_people_found(
    account_id: UUID, idempotency_id_prefix: str, full_transcript: str
) -> bool:
    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=account_id,
        idempotency_id=f"{idempotency_id_prefix}-no-people-found",
        subject="Unfortunately, I did not found people in your recent voice note",
    )

    if full_transcript is None or len(str(full_transcript)) == 0:
        full_transcript = "<NOTHING>"
    email_params.body_html = simple_email_body_html(
        title=email_params.subject,
        content_text="""
    <p>I tried my best, but I couldn't figure out who you talked about in your note. This is what I understood:</p>
    <p style="line-height: 1.5;">{full_transcript}</p>""".format(
            full_transcript=full_transcript
        ),
    )

    return send_email(params=email_params)


def send_technical_failure_email(
    err: Exception,
    idempotency_id: str = str(uuid.uuid4()),
    data_entry: Optional[BaseDataEntry] = None,
) -> bool:
    # Gets the most recent Exception, get it ASAP as I know my code quality
    trace = traceback.format_exc()
    subject = str(err)
    if len(subject) > 100:
        subject = subject[:97] + "..."

    email_params = EmailLog(
        sender=SENDER_EMAIL_ALERTS,
        recipient="alerts@dumpsheet.com",
        recipient_full_name="Peter Csiba",
        subject=f"[ERROR] Dumpsheet Docker Lambda: {subject}",
        reply_to=NO_REPLY_EMAIL,  # We skip the orig_to_address, as that would trigger another transcription.
        idempotency_id=idempotency_id,
    )
    # TODO(devx, P1): Would be great to include last 10 log messages for even faster debugging.
    # Note: No need to format - less code less bugs.
    email_params.body_html = f"<p>{str(err)}</p>" + trace.replace("\n", "<br />")

    if bool(data_entry):
        identity = EmailLog.get_email_reply_params_for_account_id(
            data_entry.account_id, idempotency_id, subject="whatever"
        )
        transcript = str(data_entry.output_transcript)
        if len(transcript) > 200:
            transcript = subject[:197] + "..."

        email_params.body_html += """
            <p><b>User Email:</b> {email}</p>
            <p><b>User Full Name:</b> {full_name}</p>
            <p style="line-height: 1.5;"><b>Transcript:</b> {transcript}</p>
        """.format(
            email=identity.recipient,
            full_name=identity.recipient_full_name,
            transcript=transcript,
        )

    result = send_email(params=email_params)

    # This is non-blocking on failure
    twilio_client = TwilioClient()
    twilio_client.send_sms(
        "+16502106516", f"You got a new alert from Poor Mans Opsgenie: {subject}"
    )

    return result


# We use data_entry_id, as the underlying account_id can change in the demo onboarding flow
# Yeah, I know it's kinda junk - we try to track how users come to the platform and merge same emails.
# NOTE: Maximum Lambda run-time is 15 minutes, so waiting longer does not make sense.
def wait_for_email_updated_on_data_entry(
    data_entry_id: UUID, max_wait_seconds: int = 10 * 60, wait_cycle_seconds: int = 10
) -> bool:
    start_time = time.time()
    end_time = start_time + max_wait_seconds

    while time.time() < end_time:
        updated_data_entry = BaseDataEntry.get_by_id(data_entry_id)
        account_id = updated_data_entry.account_id
        acc: Account = Account.get_by_id(account_id)
        if acc.get_email() is not None:
            print(f"account {account_id} has email set")

            # TODO(P2, hack): This is the multi-channel onboarding flow account consolidation hack
            if bool(acc.merged_into_id) and account_id != acc.merged_into_id:
                print(
                    f"fixing up data entry to redirect account_id {account_id} to {acc.merged_into_id}"
                )
                updated_data_entry.account_id = acc.merged_into_id
                updated_data_entry.save()

            return True

        print(
            f"waiting {wait_cycle_seconds} seconds for user to input their email address"
        )
        time.sleep(wait_cycle_seconds)

    return False


if __name__ == "__main__":
    human_readable_tests = [
        "2023-10-05_193824-0500-James_white_for_testing.m4a",
        "2023-10-06_210315-0500-Andrej_Jursa_Vestberry.m4a.mp4",
        "2023-10-20_090550-0700-Lisa_from_Roo_-_LBS.m4a",  # with an extra dash
    ]
    for test_case in human_readable_tests:
        print(_make_human_readable(test_case))
