from hubspot import HubSpot
from hubspot.auth import oauth
from hubspot.crm import contacts

from common.config import HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET

api_client = HubSpot()

try:
    tokens = api_client.auth.oauth.tokens_api.create(
        grant_type="authorization_code",
        redirect_uri="http://localhost",
        client_id=HUBSPOT_CLIENT_ID,
        client_secret=HUBSPOT_CLIENT_SECRET,
        code="authorization_code_obtained_from_user",
    )
    access_token = tokens.access_token
    api_client.access_token = access_token  # Setting the access token for further use
except oauth.ApiException as e:
    print(f"Exception when fetching access token: {e}")

try:
    simple_public_object_input_for_create = contacts.SimplePublicObjectInputForCreate(
        properties={"email": "email@example.com"}
    )
    api_response = api_client.crm.contacts.basic_api.create(
        simple_public_object_input_for_create=simple_public_object_input_for_create
    )
    print(f"Contact created: {api_response}")
except contacts.ApiException as e:
    print(f"Exception when creating contact: {e}")
