import os

from dotenv import load_dotenv

load_dotenv()

# AWS stuff
DEFAULT_REGION = "us-west-2"

# EMAIL Stuff
SENDER_EMAIL = "Your Sidekick Voxana <sidekick@voxana.ai>"  # From:
SUPPORT_EMAIL = "Voxana.AI <support@voxana.ai>"
DEBUG_RECIPIENTS = ["email-archive@voxana.ai"]

# OPENAI STUFF
OPEN_AI_API_KEY: str = os.environ.get("OPEN_AI_API_KEY")

# SUPABASE STUFF
SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY")
