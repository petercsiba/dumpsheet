import datetime
import time
import uuid

from hubspot import HubSpot
from hubspot.auth import oauth
from hubspot.crm import contacts

from common.config import HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET, HUBSPOT_REDIRECT_URL
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from database.models import BaseAccount, BaseOnboarding, BaseOrganization
from database.organization import ORGANIZATION_ROLE_ADMIN


class HubspotClient:
    def __init__(self, organization_id: uuid.UUID):
        self.api_client = HubSpot()
        self.expires_at_cache = None
        self.organization_id = organization_id
        self._ensure_token_fresh()

    # TODO(P0, bug): We have to somehow use the refresh token to get new access_tokens
    # https://legacydocs.hubspot.com/docs/methods/oauth2/oauth2-quickstart#refreshing-oauth-20-tokens
    def _ensure_token_fresh(self):
        if self.expires_at_cache is None:
            organization = BaseOrganization.get_by_id(self.organization_id)
            self.expires_at_cache = organization.hubspot_expires_at
            if bool(self.expires_at_cache):
                self.api_client.access_token = organization.hubspot_access_token

        if (
            self.expires_at_cache is None
            or self.expires_at_cache < datetime.datetime.now()
        ):
            print(f"gonna refresh token for organization {self.organization_id}")
            try:
                organization = BaseOrganization.get_by_id(self.organization_id)

                # We assume the Auth was already granted, and that the Organization already has a refresh_token there.
                tokens = self.api_client.auth.oauth.tokens_api.create(
                    grant_type="refresh_token",
                    client_id=HUBSPOT_CLIENT_ID,
                    client_secret=HUBSPOT_CLIENT_SECRET,
                    redirect_uri=HUBSPOT_REDIRECT_URL,
                    refresh_token=organization.hubspot_refresh_token,
                )
                organization.hubspot_access_token = tokens.access_token
                organization.hubspot_refresh_token = tokens.refresh_token
                # We subtract 60 seconds to make more real.
                organization.expires_at = datetime.datetime.now() + datetime.timedelta(
                    seconds=tokens.expires_in - 60
                )
                organization.save()

                self.expires_at_cache = organization.expires_at
                self.api_client.access_token = organization.hubspot_access_token
                print(f"token refreshed, expires at {self.expires_at_cache}")
            except oauth.ApiException as e:
                print(f"Exception when fetching access token: {e}")

    def crm_contact_create(self):
        self._ensure_token_fresh()
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
        self._ensure_token_fresh()
        try:
            # Handles the pagination with default limit = 100
            api_response = self.api_client.crm.contacts.get_all()
            print(f"Contacts listed: {api_response}")
        except contacts.ApiException as e:
            print(f"Exception when creating contact: {e}")


if __name__ == "__main__":
    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        fixture_exists = BaseOrganization.get_or_none(
            BaseOrganization.name == "testing locally"
        )
        if bool(fixture_exists):
            organization_id = fixture_exists.id
            print(f"reusing testing fixture for organization {organization_id}")
        else:
            # Fixtures from prod
            organization_id = BaseOrganization.insert(
                hubspot_refresh_token="9ce60291-2261-48a5-8ddb-e26c9bf59845",  # TestApp - hardcoded each time
                hubspot_linked_at=datetime.datetime.now(),
                name="testing locally",
            ).execute()

        account_id = BaseAccount.insert(
            full_name="peter csiba",
            organization_id=organization_id,
            organization_role=ORGANIZATION_ROLE_ADMIN,
        ).execute()
        BaseOnboarding.insert(
            email="petherz+localhost@gmail.com",
            account_id=account_id,
        )

        client = HubspotClient(organization_id)
        # client.auth_account_id(uuid.UUID("3776ef1f-23a0-43e8-b275-ba45e5af9dea"))
        client.crm_contact_create()
        client.crm_contact_get_all()
