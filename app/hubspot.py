import uuid

from hubspot import HubSpot
from hubspot.auth import oauth
from hubspot.crm import contacts

from common.config import HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET, HUBSPOT_REDIRECT_URL
from database.models import BaseAccount, BaseOrganization


class HubspotClient:
    def __init__(self):
        self.api_client = HubSpot()

    def auth_account_id(self, account_id: uuid.UUID):
        acc: BaseAccount = BaseAccount.get_by_id(account_id)
        org: BaseOrganization = BaseOrganization.get_by_id(acc.id)

        try:
            # TODO(P1, hubspot): I am a bit confused on how the hubspot id will be passed :/
            tokens = self.api_client.auth.oauth.tokens_api.create(
                grant_type="authorization_code",
                redirect_uri=HUBSPOT_REDIRECT_URL,
                client_id=HUBSPOT_CLIENT_ID,
                client_secret=HUBSPOT_CLIENT_SECRET,
                code=org.hubspot_code,
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
                    properties={"email": "email@example.com"}
                )
            )
            api_response = self.api_client.crm.contacts.basic_api.create(
                simple_public_object_input_for_create=simple_public_object_input_for_create
            )
            print(f"Contact created: {api_response}")
        except contacts.ApiException as e:
            print(f"Exception when creating contact: {e}")
