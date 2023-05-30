import boto3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


def create_raw_email_with_attachments(subject, body_html, sender, recipients, attachment_paths=None):
    if attachment_paths is None:
        attachment_paths = []

    # Create a multipart/mixed parent container
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

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
