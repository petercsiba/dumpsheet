import os

from dotenv import load_dotenv

load_dotenv()

ENV = os.environ.get("ENV")
ENV_PROD = "prod"
ENV_LOCAL = "local"
ENV_TEST = "test"

# Launch / back-fill controls
ALLOW_ONBOARDING_IP_MATCHING = os.environ.get("ALLOW_ONBOARDING_IP_MATCHING", "0")
SKIP_SHARE_SPREADSHEET = os.environ.get("SKIP_SHARE_SPREADSHEET", "0")
SKIP_PROCESSED_DATA_ENTRIES = os.environ.get("SKIP_PROCESSED_DATA_ENTRIES", "1")
SKIP_SENDING_EMAILS = os.environ.get("SKIP_SENDING_EMAILS", "0")

# AWS stuff
DEFAULT_REGION = "us-west-2"
AWS_ACCESS_KEY_ID: str = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY: str = os.environ.get("AWS_SECRET_ACCESS_KEY")

# EMAIL Stuff
NO_REPLY_EMAIL = "No Reply <no-reply@mail.dumpsheet.com>"
SENDER_EMAIL = "Dumpsheet Workers Union<worker@mail.dumpsheet.com>"  # From:
SENDER_EMAIL_ALERTS = "Poor Mans Opsgenie <alerts@mail.dumpsheet.com>"  # From:
SUPPORT_EMAIL = "Dumpsheet Support <support@dumpsheet.com>"
DEBUG_RECIPIENTS = ["email-archive@dumpsheet.com"]
RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS = int(
    os.environ.get("RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS", 30)
)

GOOGLE_FORMS_SERVICE_ACCOUNT_PRIVATE_KEY = os.environ.get(
    "GOOGLE_FORMS_SERVICE_ACCOUNT_PRIVATE_KEY", ""
).replace("|", "\n")

# HUBSPOT STUFF https://app.hubspot.com/developer/43920988/application/2150554/?tab=auth
ADMIN_CONSOLE_HUBSPOT_REFRESH_TOKEN = os.environ.get(
    "ADMIN_CONSOLE_HUBSPOT_REFRESH_TOKEN"
)
HUBSPOT_APP_ID = "2150554"
HUBSPOT_CLIENT_ID = "501ffe58-5d49-47ff-b41f-627fccc28715"
HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET")
HUBSPOT_REDIRECT_URL = "https://api.dumpsheet.com/hubspot/oauth/redirect"

# OPENAI STUFF
OPEN_AI_API_KEY: str = os.environ.get("OPEN_AI_API_KEY")
