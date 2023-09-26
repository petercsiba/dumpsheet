import time
import uuid

from hubspot import HubSpot
from hubspot.auth import oauth
from hubspot.crm import contacts

from common.config import HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET, HUBSPOT_REDIRECT_URL
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres


class HubspotClient:
    def __init__(self):
        self.api_client = HubSpot()

    # TODO(P0, bug): We have to somehow use the refresh token to get new access_tokens
    # https://legacydocs.hubspot.com/docs/methods/oauth2/oauth2-quickstart#refreshing-oauth-20-tokens
    def auth_account_id(self, account_id: uuid.UUID):
        # acc: BaseAccount = BaseAccount.get_by_id(account_id)
        # org: BaseOrganization = BaseOrganization.get_by_id(acc.id)

        try:
            # TODO(P1, hubspot): I am a bit confused on how the hubspot id will be passed :/
            tokens = self.api_client.auth.oauth.tokens_api.create(
                grant_type="authorization_code",
                redirect_uri=HUBSPOT_REDIRECT_URL,
                client_id=HUBSPOT_CLIENT_ID,
                client_secret=HUBSPOT_CLIENT_SECRET,
                # code=org.hubspot_code,
                # code="bc606926-ab53-4907-9f24-032b0feec832",  # RealApp (expired)
                code="2892f46c-3fc3-4dd3-bf5d-70d147818495",  # TestApp
            )
            access_token = tokens.access_token
            self.api_client.access_token = (
                access_token  # Setting the access token for further use
            )
        except oauth.ApiException as e:
            print(f"Exception when fetching access token: {e}")

    def crm_contact_create(self):
        try:
            simple_public_object_input_for_create = (
                contacts.SimplePublicObjectInputForCreate(
                    properties={"email": f"email+{int(time.time())}@example.com"}
                )
            )
            api_response = self.api_client.crm.contacts.basic_api.create(
                simple_public_object_input_for_create=simple_public_object_input_for_create
            )
            print(f"Contact created: {api_response}")
        except contacts.ApiException as e:
            print(f"Exception when creating contact: {e}")

    def crm_contact_get_all(self):
        try:
            # Handles the pagination with default limit = 100
            api_response = self.api_client.crm.contacts.get_all()
            print(f"Contacts listed: {api_response}")
        except contacts.ApiException as e:
            print(f"Exception when creating contact: {e}")


if __name__ == "__main__":
    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        client = HubspotClient()
        client.auth_account_id(uuid.UUID("3776ef1f-23a0-43e8-b275-ba45e5af9dea"))
        client.crm_contact_create()
        client.crm_contact_get_all()
