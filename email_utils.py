import email
import os

# Parse the email
with open("example-email.mime", "r") as handle:
    msg = email.message_from_file(handle)
    # msg = email.message_from_bytes(raw_email)

    # Process the attachments
    for part in msg.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') is None:
            continue

        # TODO: Support multiple attacjments
        # Get the attachment's filename
        file_name = part.get_filename()
        print(f"file_name: {file_name}")

        if bool(file_name):
            # If there is an attachment, save it to a file
            file_path = os.path.join('/tmp/', file_name)
            if not os.path.isfile(file_path):
                with open(file_path, 'wb') as f:
                    f.write(part.get_payload(decode=True))