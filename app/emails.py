import boto3
import datetime
import pytz
import os

from bs4 import BeautifulSoup

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from storage_utils import pretty_filesize

SENDER_EMAIL = "Katka.AI <assistant@katka.ai>"  # From:
DEBUG_RECIPIENTS = ["petherz@gmail.com", "kata.sabo@gmail.com"]


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


def create_raw_email_with_attachments(
        subject,
        body_html,
        sender,
        to: list,
        bcc: list,
        reply_to: list,
        attachment_paths=None
):
    if attachment_paths is None:
        attachment_paths = []

    # Create a multipart/mixed parent container
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(to)
    msg['Reply-To'] = ", ".join(reply_to)
    msg['Bcc'] = ', '.join(bcc)
    print(f"Sending email from {msg['From']} to {msg['To']} (and bcc {msg['Bcc']} with subject {msg['Subject']}")

    # Create a multipart/alternative child container
    msg_body = MIMEMultipart('alternative')

    # Encode the text and add it to the child container
    textpart = MIMEText(body_html, 'html')
    msg_body.attach(textpart)

    # Attach the multipart/alternative child container to the multipart/mixed parent container
    msg.attach(msg_body)

    # Add attachments
    for attachment_path in attachment_paths:
        with open(attachment_path, 'rb') as file:
            attachment = MIMEApplication(file.read())
        # Define the content ID
        attachment.add_header('Content-Disposition', 'attachment', filename=attachment_path.split('/')[-1])
        # Add the attachment to the parent container
        msg.attach(attachment)

    return msg


# TODO: Move the logic of parsing the email attachment to here


def send_email(email_address, subject, body_text, attachment_paths=None):
    if not isinstance(email_address, str):
        print(f"email_adress is NOT a string {email_address}, falling back to {DEBUG_RECIPIENTS}")
        email_address = DEBUG_RECIPIENTS[0]

    ses = boto3.client('ses')
    sender = SENDER_EMAIL
    recipients = [email_address]
    bcc_recipients = list(set(DEBUG_RECIPIENTS) - {email_address})
    body_html = """<html>
    <head></head>
    <body>
      """ + body_text + """
    </body>
    </html>
    """

    # Create the raw email
    raw_email = create_raw_email_with_attachments(
        subject,
        body_html,
        sender=sender,
        to=recipients,
        bcc=bcc_recipients,
        reply_to=DEBUG_RECIPIENTS,
        attachment_paths=attachment_paths,
    )

    try:
        print(f"Attempting to send email to {recipients} with attached files {attachment_paths}")
        response = ses.send_raw_email(
            Source=sender,
            Destinations=recipients + bcc_recipients,
            RawMessage={
                'Data': raw_email.as_string(),
            }
        )
        print(f'Email sent! Message ID: {response["MessageId"]}, Subject: {subject}')
    except Exception as e:
        print(f'Email with subjectL {subject} failed to send. {e}')


# TODO(P1): Move email templates to separate files - ideally using a standardized template language like handlebars.
def send_confirmation(email_address: str, sender_first_name: str, attachment_file_paths: list):
    if len(attachment_file_paths) == 0:
        subject = f"Yo {sender_first_name} - where is the attachment?"
        body_text = ("""
            <h3>Hello there""" + sender_first_name + """! 👋</h3>
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
        send_email(email_address, subject, body_text)
    else:
        file_list = []
        for file_path in attachment_file_paths:
            file_size = pretty_filesize(file_path)
            file_list.append(f"<li>{os.path.basename(file_path)} ({file_size})</li>")
        file_list_str = "\n".join(file_list)

        subject = f"Hey {sender_first_name} - got your recording and I am already crunching through it!"
        body_text = ("""
    <h3>Hello there """ + sender_first_name + """! 👋</h3>
    <p>Thanks for trying out katka.ai - your personal networking assistant - aka the backoffice guru who takes care 
        of the admin so that you can focus on what truly matters.</p>
    <p>Guess what? 🎉 I've received the following files:</p>
    <ul>""" + f"{file_list_str}" + """</ul>
    <p>No worries, I'll handle them swiftly like a pro. This task should take me approximately 2-15 minutes. ⏱️</p>
    <h3>Got any questions? 🔥</h3>""" +
                     f"<p>Feel free to hit reply or reach out to my supervisors at {DEBUG_RECIPIENTS}. "
                     f"They're here to assist you with anything you need. 📞👩‍💼👨‍💼</p>" +
                     """<p>Keep rocking it!</p>
    <p>Your amazing team at katka.ai 🚀</p>
        """)
        send_email(email_address, subject, body_text)


def send_response(email_address, email_datetime, webpage_link, attachment_paths, people_count, drafts_count):
    # TODO(P1): Generate with GPT ideally personalized to the transcript.

    # TODO(P0): Update the subject to be different.
    email_dt_str = email_datetime.strftime('%B %d, %H:%M')
    now = datetime.datetime.now(pytz.utc)
    try:
        time_to_generate = now - email_datetime
        total_seconds = int(time_to_generate.total_seconds())
        minutes, seconds = divmod(total_seconds, 60)
        to_generate_str = f'{minutes} minutes {seconds} seconds'
    except Exception as err:
        print(f"couldn't get time-to-generate for {now} - {email_datetime}")
        to_generate_str = "unknown"

    subject = f"The summary from your event sent at {email_dt_str} is ready for your review!"
    body_text = (
        "  <h3>Hey there! 👋</h3>     "
        "  <p>Looks like you had a great time at your recent event! Excellent job!</p>     "
        "  <p><strong>Here's a little recap of your success:</strong></p>     "
        "  <ul>     "
        f"      <li>You had the chance to meet {people_count} impressive individuals. 🤝</li>     "
        f"      <li>And you've got {drafts_count} potential actions to choose from, "
        f"          complete with drafted messages to start building those new relationships.</li>     "
        "  </ul>     "
        "  <h4>Now, let's discuss what's next, shall we? 💪</h4>     "
        "  <p><strong>Here's your game plan:</strong></p>     "
        "  <ul>     "
        f"      <li>First, head over to <a href=\"{webpage_link}\">your event summary from {email_dt_str}</a>. "
        f"          It's your directory of people with proposed draft messages. ✉️</li>     "
        "      <li>Choose the one draft that suits your style, personalize it if necessary, "
        "          and hit send to start building your new connections. 📧</li>     "
        "      <li>We've also attached a detailed table of all the key summaries for your excel-cirse skills. 📊</li>     "
        "  </ul>     "
        "  <p>Have any questions? No problem! 😊</p>     "
        f"  <p>Just hit reply or send an email to my supervisors at {DEBUG_RECIPIENTS}. "
        "      They're here to help. 👍</p>     "
        "  <h4>Keep up the great work! 💪</h4>     "
        "  <p>Your team at katka.ai</p>     "
        f"This summary took {to_generate_str} to generate"
    )
    send_email(email_address, subject, body_text, attachment_paths)
