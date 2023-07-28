import os

from dotenv import load_dotenv

load_dotenv()

# AWS stuff
DEFAULT_REGION = "us-west-2"

# EMAIL Stuff
NO_REPLY_EMAIL = "No Reply <no-reply@mail.voxana.ai>"
SENDER_EMAIL = "Voxana Assistant <assistant@mail.voxana.ai>"  # From:
SENDER_EMAIL_ALERTS = "Poor Mans Opsgenie <alerts@mail.voxana.ai>"  # From:
SUPPORT_EMAIL = "Voxana.AI <support@voxana.ai>"
DEBUG_RECIPIENTS = ["email-archive@voxana.ai"]
RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS = int(
    os.environ.get("RESPONSE_EMAILS_WAIT_BETWEEN_EMAILS_SECONDS", 30)
)

# OPENAI STUFF
OPEN_AI_API_KEY: str = os.environ.get("OPEN_AI_API_KEY")

# SUPABASE STUFF
SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY")
