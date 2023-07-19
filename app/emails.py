import copy
import os
import time
import traceback
from email.header import decode_header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Dict

import boto3
from bs4 import BeautifulSoup

from common.aws_utils import is_running_in_aws
from common.config import DEBUG_RECIPIENTS, SUPPORT_EMAIL
from common.storage_utils import pretty_filesize_path
from db.email_log import EmailLog


def store_and_get_attachments_from_email(msg):
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
        file_name = f"{time.time()}-{orig_file_name}"
        file_path = os.path.join("/tmp/", file_name)
        with open(file_path, "wb") as f:
            f.write(part.get_payload(decode=True))

        attachment_file_paths.append(file_path)
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


# TODO(P1, features): Potentially use multi-part emails with this function
def get_text_from_email(msg):
    print("get_text_from_email")
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                print("multipart: found a text/plain")
                parts.append(part.get_payload(decode=True).decode())
            elif part.get_content_type() == "text/html":
                print("multipart: found a text/html")
                soup = BeautifulSoup(part.get_payload(decode=True), "html.parser")
                text = soup.get_text()
                parts.append(text)
    elif msg.get_content_type() == "text/plain":
        print("single-part: found a text/plain")
        parts.append(msg.get_payload(decode=True).decode())
    elif msg.get_content_type() == "text/html":
        print("single-part: found a text/html")
        soup = BeautifulSoup(msg.get_payload(decode=True), "html.parser")
        text = soup.get_text()
        parts.append(text)

    result = " ".join(parts)
    print(
        f"get_text_from_email: total {len(parts)} found with {len(result.split())} tokens"
    )
    return result


def create_raw_email_with_attachments(params: EmailLog):
    if not isinstance(params.recipient, str):
        print(
            f"email_address is NOT a string {params.recipient}, falling back to {DEBUG_RECIPIENTS}"
        )
        params.recipient = DEBUG_RECIPIENTS[0]
    # Fill in sender name
    sender_name, sender_email = parseaddr(params.sender)
    if sender_name == "":
        params.sender = f"voxana.AI Assistant <{sender_email}>"

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

    if params.check_if_already_sent():
        print(
            f"SKIPPING email '{params.idempotency_id}' cause already sent for {params.user}"
        )
        return True

    if not is_running_in_aws():
        # TODO(P2, testing): Ideally we should also test the translation from params to raw email.
        print(
            f"Skipping ses.send_raw_email cause NOT in AWS. Dumping the email {params.idempotency_id} contents {params}"
        )
        params.log_email()
        return True
    try:
        print(
            f"Attempting to send email {params.idempotency_id} to {params.recipient}"
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


def add_signature():
    return """
    <h3>Got any questions?</h3>
        <p>Just hit reply. My supervisors are here to assist you with anything you need. 📞👩‍💼👨‍💼</p>
        <p>Your team at https://www.voxana.ai</p>
    """


# TODO(P1): Move email templates to separate files - ideally using a standardized template language like handlebars.
#   * Yeah, we might want to centralize this into Hubspot Transactional email API.
# We have attachment_paths separate, so the response email doesn't re-attach them.
def send_confirmation(params: EmailLog, attachment_paths):
    if len(attachment_paths) == 0:
        params.body_text = (
            """
            <h3>Yo """
            + params.get_recipient_first_name()
            + """, did you forgot the attachment?</h3>
        <p>Thanks for using voxana.ai - your personal networking assistant -
        aka the backoffice hero who takes care of the admin so that you can focus on what truly matters.</p>
        <p>But yo boss, where is the attachment? ☕ I would love to brew you a coffee, but I ain't real,
        so an emoji will have to do it: ☕</p>
        <p>Remember, any audio file would do, I can convert stuff myself! 🎧</p>
        """
            + add_signature()
        )
        params.idempotency_id = f"{params.idempotency_id}-forgot-attachment"
        send_email(params=params)
    else:
        file_list = []
        for file_path in attachment_paths:
            file_size = pretty_filesize_path(file_path)
            file_list.append(f"<li>{os.path.basename(file_path)} ({file_size})</li>")
        file_list_str = "\n".join(file_list)

        # TODO: should this be body_html?
        params.body_text = (
            """
    <h3>Hello there """
            + params.get_recipient_first_name()
            + """! 👋</h3>
        <p>Thanks for using voxana.ai - your personal networking assistant - aka the backoffice guru who takes care
            of the admin so that you can focus on what truly matters.</p>
    <h3>Rest assured, I got your recording and I am already crunching through it!</h3>
        <p>I've received the following files:</p>
        <ul>"""
            + f"{file_list_str}"
            + """</ul>
    <h3>What's next?</h3>
        <ul>
            <li> Relax for about 2 to 10 minutes until I work through your brain-dump boss. ⏱️️</li>
            <li> Be on a look-out for an email from """
            + params.sender
            + """</li>
        </ul>
        """
            + add_signature()
        )
        params.idempotency_id = f"{params.idempotency_id}-confirmation"
        send_email(params=params)


def send_responses(
    orig_email_params: EmailLog,
    actions: Dict[str, str],
):
    i = 0
    for subject, body in actions.items():
        i += 1
        email_params = copy.deepcopy(orig_email_params)
        email_params.subject = subject
        # TODO(P1, ux): The button seems to NOT render - investigate why.
        email_params.body_text = (
            f"  <h3>{subject}</h3>"
            "  <p>I have crunched through your brain dump and for this action I propose the following draft</p>"
            # TODO(P0, ux): Format this with bullet points
            f" <p>{body}</p>" + add_signature()
        )
        email_params.idempotency_id = f"{orig_email_params.idempotency_id}-{i}"
        send_email(params=email_params)
