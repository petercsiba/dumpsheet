from email.header import decode_header
from typing import Optional

import boto3
import datetime
import pytz
import os
import time
import traceback

from bs4 import BeautifulSoup

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import parseaddr

from aws_utils import is_running_in_aws, get_dynamo_endpoint_url
from datashare import EmailParams, EmailLog
from dynamodb import TABLE_NAME_EMAIL_LOG, read_data_class, write_data_class
from openai_client import PromptStats
from storage_utils import pretty_filesize

SENDER_EMAIL = "Katka.AI <assistant@katka.ai>"  # From:
DEBUG_RECIPIENTS = ["petherz@gmail.com", "kata.sabo@gmail.com"]


def store_and_get_attachments_from_email(msg):
    # Process the attachments
    attachment_file_paths = []
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        # Get the attachment's filename
        orig_file_name = part.get_filename()
        print(f"Parsing attachment {orig_file_name}")

        if not bool(orig_file_name):
            continue

        # If there is an attachment, save it to a file
        file_name = f"{time.time()}-{orig_file_name}"
        file_path = os.path.join('/tmp/', file_name)
        with open(file_path, 'wb') as f:
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
            decoded_parts.append(part.decode('us-ascii'))
        else:
            # already str in us-ascii encoding
            decoded_parts.append(part)
    return ' '.join(decoded_parts)


def get_email_params_for_reply(msg):
    # The variable naming is a bit confusing here, as `msg` refers to received email,
    # while all the returned Email params are for the reply (i.e. recipient = reply_to)
    email_from = msg.get('From')
    orig_to_address = msg.get('To')
    orig_subject = msg.get('Subject')
    # Parse the address
    sender_full_name, sender_email_addr = parseaddr(email_from)
    sender_full_name = "Person" if sender_full_name is None else decode_str(sender_full_name)
    reply_to_address = msg.get('Reply-To')
    if reply_to_address is None or not isinstance(reply_to_address, str):
        print("No reply-to address provided, falling back to from_address")
        reply_to_address = sender_email_addr
    print(
        f"email from {sender_full_name} ({sender_email_addr}) reply-to {reply_to_address} "
        f"orig_to_address {orig_to_address}, orig_subject {orig_subject}"
    )
    return EmailParams(
        sender=orig_to_address,
        recipient=reply_to_address,
        recipient_full_name=sender_full_name,
        subject=f"Re: {orig_subject}",
        reply_to=DEBUG_RECIPIENTS,  # We skip the orig_to_address, as that would trigger another transcription.
    )


# TODO(P0): Have a way to test email-renderings for bugs before deployment.
def get_text_from_email(msg):
    print("get_text_from_email")
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                print("multipart: found a text/plain")
                parts.append(part.get_payload(decode=True).decode())
            elif part.get_content_type() == 'text/html':
                print("multipart: found a text/html")
                soup = BeautifulSoup(part.get_payload(decode=True), 'html.parser')
                text = soup.get_text()
                parts.append(text)
    elif msg.get_content_type() == 'text/plain':
        print("single-part: found a text/plain")
        parts.append(msg.get_payload(decode=True).decode())
    elif msg.get_content_type() == 'text/html':
        print("single-part: found a text/html")
        soup = BeautifulSoup(msg.get_payload(decode=True), 'html.parser')
        text = soup.get_text()
        parts.append(text)

    result = " ".join(parts)
    print(f"get_text_from_email: total {len(parts)} found with {len(result.split())} tokens")
    return result


def create_raw_email_with_attachments(params: EmailParams):
    if not isinstance(params.recipient, str):
        print(f"email_address is NOT a string {params.recipient}, falling back to {DEBUG_RECIPIENTS}")
        params.recipient = DEBUG_RECIPIENTS[0]
    # Fill in sender name
    sender_name, sender_email = parseaddr(params.sender)
    if sender_name == "":
        params.sender = f"Katka.AI Assistant <{sender_email}>"

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
        params.body_html = """<html>
        <head></head>
        <body>
          """ + params.body_text + """
        </body>
        </html>
        """

    # Create a multipart/mixed parent container
    msg = MIMEMultipart('mixed')
    msg['Subject'] = params.subject
    msg['From'] = params.sender
    msg['To'] = params.recipient
    msg['Reply-To'] = ", ".join(params.reply_to)
    if params.bcc is not None:
        msg['Bcc'] = ', '.join(params.bcc)

    print(f"Sending email from {msg['From']} to {msg['To']} (and bcc {msg['Bcc']}) with subject {msg['Subject']}")

    # Create a multipart/alternative child container
    msg_body = MIMEMultipart('alternative')

    # Encode the text and add it to the child container
    msg_body.attach(MIMEText(params.body_html, 'html'))

    # Attach the multipart/alternative child container to the multipart/mixed parent container
    msg.attach(msg_body)

    # Add attachments
    for attachment_path in params.attachment_paths:
        with open(attachment_path, 'rb') as file:
            attachment = MIMEApplication(file.read())
        # Define the content ID
        attachment.add_header('Content-Disposition', 'attachment', filename=attachment_path.split('/')[-1])
        # Add the attachment to the parent container
        msg.attach(attachment)

    return msg


def get_email_log_table():
    dynamodb = boto3.resource('dynamodb', endpoint_url=get_dynamo_endpoint_url())
    return dynamodb.Table(TABLE_NAME_EMAIL_LOG)


def check_if_already_sent(email_to: str, idempotency_key: Optional[str]):
    if idempotency_key is None:
        return False

    email_log_table = get_email_log_table()
    previous_email: EmailLog = read_data_class(data_class_type=EmailLog, table=email_log_table, key={
        'email_to': email_to,
        'idempotency_key': idempotency_key,
    }, print_not_found=True)
    return previous_email is not None


def log_email(email_params: EmailParams, idempotency_key: Optional[str]):
    if idempotency_key is None:
        return None

    email_log_table = get_email_log_table()
    item = EmailLog(
        email_to=email_params.recipient,
        idempotency_key=idempotency_key,
        params=email_params,
    )
    return write_data_class(table=email_log_table, data=item)
    

# TODO(P2): Gmail marks us as spam - no clear way around it. Some easy-ish ways:
#     * [DONE] Use the same email sender address
#     * [DONE] Authenticate emails DKIM, DMARC, SPF
#     * Next(Mehdi): "Prime" your domain, blast emails, make everyone to open it (this will happen over time).
#     * Add Unsubscribe button
#     * Opt-in process (verify email)
#     * Over-time, the higher the engagement with our emails the better.
def send_email(params: EmailParams, idempotency_key: Optional[str] = None) -> bool:
    params.bcc = DEBUG_RECIPIENTS
    raw_email = create_raw_email_with_attachments(params)

    if check_if_already_sent(params.recipient, idempotency_key=idempotency_key):
        print(f"Email '{idempotency_key}' already sent for {params.recipient} - skipping send.")
        return True

    if not is_running_in_aws():
        # TODO(P1, testing): Would be nice to pass in the local dynamodb for testing the cache - BUT then mostly
        #   relevant for prod.
        # TODO(P2, testing): Ideally we should also test the translation from params to raw email.
        print(f"Skipping ses.send_raw_email cause NOT in AWS. Dumping the email {idempotency_key} contents {params}")
        log_email(email_params=params, idempotency_key=idempotency_key)
        return True
    try:
        print(
            f"Attempting to send email {idempotency_key} to {params.recipient}"
            f"with attached files {params.attachment_paths}"
        )

        ses = boto3.client('ses')
        response = ses.send_raw_email(
            Source=params.sender,
            # TIL, list(str) returns characters, instead of having a single entry list [str]
            Destinations=[params.recipient] + params.bcc,
            RawMessage={
                'Data': raw_email.as_string(),
            },
            # TODO(P1, cx): We need DB for this too, as MessageDeduplicationId is for SQS (and this is SES).
            #   check_message_id_in_database, store_message_id_in_database (anyway would be nice to store all msgs)
            # MessageDeduplicationId=dedup_id,
        )

        message_id = response["MessageId"]
        print(f'Email sent! Message ID: {message_id}, Subject: {params.subject}')

        log_email(email_params=params, idempotency_key=idempotency_key)
        return True
    except Exception as e:
        print(f'Email with subject {params.subject} failed to send. {e}')
        traceback.print_exc()
        return False


# TODO(P1): Move email templates to separate files - ideally using a standardized template language like handlebars.
#   * OR maybe even to SES.
def send_confirmation(params: EmailParams, dedup_prefix=None):
    if len(params.attachment_paths) == 0:
        params.body_text = ("""
            <h3>Yo """ + params.get_recipient_first_name() + """, did you forgot the attachment?</h3>
        <p>Thanks for trying out katka.ai - your personal networking assistant - 
        aka the backoffice hero who takes care of the admin so that you can focus on what truly matters.</p>
        <p>But yo boss, where is the attachment? ☕ I would love to brew you a coffee, but I ain't real, 
        so an emoji will have to do it: ☕</p>
        <p>Remember, any audio file would do, I can convert stuff myself! 🎧</p>
    <h3>Got any questions? 🔥</h3>
        <p>Feel free to hit reply. My supervisors are here to assist you with anything you need. 📞👩‍💼👨‍💼</p>
        <p>Keep rocking it!</p>
        <p>Your amazing team at katka.ai 🚀</p>
        """)
        send_email(params=params, idempotency_key=None if dedup_prefix is None else f"{dedup_prefix}-forgot-attachment")
    else:
        file_list = []
        for file_path in params.attachment_paths:
            file_size = pretty_filesize(file_path)
            file_list.append(f"<li>{os.path.basename(file_path)} ({file_size})</li>")
        file_list_str = "\n".join(file_list)

        # subject = f"Hey {params.get_recipient_first_name()} - !"
        params.body_text = ("""
    <h3>Hello there """ + params.get_recipient_first_name() + """! 👋</h3>
        <p>Thanks for trying out katka.ai - your personal networking assistant - aka the backoffice guru who takes care 
            of the admin so that you can focus on what truly matters.</p>
    <h3>Rest assured, I got your recording and I am already crunching through it!</h3>
        <p>I've received the following files:</p>
        <ul>""" + f"{file_list_str}" + """</ul>
    <h3>What's next?</h3>
        <ul>
            <li> Relax for about 2 to 10 minutes until I work through your brain-dump boss. ⏱️️</li>
            <li> Be on a look-out for an email from """ + params.sender + """</li>
        </ul>
    <h3>Got any questions? 🔥</h3>
        <p>Feel free to hit reply or reach out to my supervisors at """ + ' or '.join(DEBUG_RECIPIENTS) + """
        They're here to assist you with anything you need. 📞👩‍💼👨‍💼</p>
        <p>Keep rocking it!</p>
        <p>Your amazing team at katka.ai 🚀</p>
        """)
        send_email(params=params, idempotency_key=None if dedup_prefix is None else f"{dedup_prefix}-confirmation")


def send_response(
        email_params: EmailParams,
        email_datetime: datetime.datetime,
        webpage_link: str,
        people_count: int,
        drafts_count: int,
        prompt_stats: PromptStats,
        idempotency_key: Optional[str],
):
    # TODO(P1, migration): Get it from DataEntry.event_name
    email_dt_str = email_datetime.strftime('%B %d, %H:%M')
    now = datetime.datetime.now(pytz.utc)
    try:
        time_to_generate = now - email_datetime
        total_seconds = int(time_to_generate.total_seconds())
        minutes, seconds = divmod(total_seconds, 60)
        to_generate_str = f'{minutes} minutes {seconds} seconds'
    except Exception as err:
        print(f"couldn't get time-to-generate for {now} - {email_datetime} cause {err}")
        to_generate_str = "unknown"

    # subject = f"The summary from your event sent at {email_dt_str} is ready for your review!"
    email_params.body_text = (
        f"  <h3>The summary from your event sent at {email_dt_str} is ready for your review!</h3>"
        "  <p>Looks like you had a great time at your recent event! Excellent job!</p>"
        "  <p><strong>Here's a little recap of your success:</strong></p>"
        "  <ul>"
        f"      <li>You had the chance to meet {people_count} impressive individuals. 🤝</li>"
        f"      <li>And you've got {drafts_count} potential actions to choose from, "
        f"          complete with drafted messages to start building those new relationships.</li>"
        "  </ul>"
        "  <h4>Now, let's discuss what's next, shall we? 💪</h4>"
        "  <p><strong>Here's your game plan:</strong></p>"
        f"<a href=\"webpage_link\"" + """ style="
                display: inline-block;
                padding: 10px 20px;
                background-color: #007BFF; /* Change the color as per your design */
                color: #ffffff;
                text-align: center;
                text-decoration: none;
                border-radius: 4px; /* Optional */
                font-size: 16px;
                line-height: 1.5;
                transition: background-color 0.3s ease;
            >
                View event summary
            </a>"""
        "  <ul>"
        f"      <li><strong>First</strong>, head over to "
        f"          <a href=\"{webpage_link}\">your event summary from {email_dt_str}</a>. "
        f"          It's your directory of people with proposed draft messages. ✉️</li>"
        "      <li>Choose the one draft that suits your style, personalize it if necessary, "
        "          and hit send to start building your new connections. 📧</li>"
        "      <li>We've also attached a detailed table of all the key summaries for your excel-cirse skills. 📊</li>"
        "  </ul>"
        "  <p>Have any questions? No problem! 😊</p>"
        f"  <p>Just hit reply or send an email to my supervisors at {' or '.join(DEBUG_RECIPIENTS)}. "
        "      They're here to help. 👍</p>"
        "  <h4>Keep up the great work! 💪</h4>"
        "  <p>Your team at katka.ai</p>"
        f"This summary took {to_generate_str} to generate using {prompt_stats.pretty_print()}"
    )
    send_email(params=email_params, idempotency_key=idempotency_key)
