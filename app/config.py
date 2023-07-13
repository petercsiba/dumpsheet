import os
from dotenv import load_dotenv

load_dotenv()

# AWS stuff
DEFAULT_REGION = "us-west-2"
DYNAMO_URL_PROD = f"https://dynamodb.{DEFAULT_REGION}.amazonaws.com"

OUTPUT_BUCKET_NAME = "katka-emails-response"  # !make sure different from the input!
# STATIC_HOSTING_BUCKET_NAME = "katka-ai-static-pages"
STATIC_HOSTING_BUCKET_NAME = "static.katka.ai"


# EMAIL Stuff
SENDER_EMAIL = "Katka.AI <assistant@katka.ai>"  # From:
SUPPORT_EMAIL = "Voxana.AI <support@voxana.ai>"
DEBUG_RECIPIENTS = ["email-archive@voxana.ai"]

# OPENAI STUFF
OPEN_AI_API_KEY: str = os.environ.get("OPEN_AI_API_KEY")

# SUPABASE STUFF
SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY")

POSTGRES_LOGIN_URL: str = os.environ.get("POSTGRES_LOGIN_URL")
