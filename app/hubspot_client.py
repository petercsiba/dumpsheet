import datetime
import json
import re
import uuid
from http import HTTPStatus

import pytz
from hubspot import HubSpot
from hubspot.auth import oauth
from hubspot.crm import contacts
from hubspot.crm.contacts import SimplePublicObjectInputForCreate
from hubspot.crm.objects import AssociationSpec, calls, tasks

from app.hubspot_models import AssociationType, FieldNames
from common.config import HUBSPOT_CLIENT_ID, HUBSPOT_CLIENT_SECRET, HUBSPOT_REDIRECT_URL
from database.models import BaseOrganization


# API Responses are just hard in general - this class tried to make it simpler but some complexity is oversimplified.
class ApiSingleResponse:
    def __init__(self, status, data, hs_object_id=None):
        self.status = status
        # Set options fields
        self.hs_object_id = hs_object_id
        self.properties = {}
        self.error = None

        if self.is_success():
            if data is not None:
                # asserting it is SimplePublicObject
                self.properties = data.properties
                if bool(self.properties):
                    self.hs_object_id = self.properties.get(FieldNames.HS_OBJECT_ID)
                if self.hs_object_id is None:
                    self.hs_object_id = data.id
        else:
            self.error = data

        # `data` has more, like ['archived', 'archived_at', 'created_at', 'properties_with_history', ...]
        # but we ignore it for now

    def is_success(self):
        return 200 <= self.status < 300

    def get_props_if_ok(self):
        return self.properties if self.is_success() else None


# Quite nice API monitoring here: https://app.hubspot.com/developer/43920988/application/2150554/monitoring/api
# TODO(P2, research): Figure out what are CRM Cards good for.
class HubspotClient:
    def __init__(self, organization_id: uuid.UUID):
        print(
            f"initializing HubspotClient client for organization_id {organization_id}"
        )
        self.api_client = HubSpot()
        self.expires_at_cache = None
        self.organization_id = organization_id
        self._ensure_token_fresh()

        # Double-check some init stuff to prevent overlong debugging
        try:
            uuid.UUID(str(HUBSPOT_CLIENT_SECRET))
        except Exception as e:
            print(
                f"WARNING: HUBSPOT_CLIENT_SECRET is expected to be an UUID, got {type(HUBSPOT_CLIENT_SECRET)}: {e}"
            )
        try:
            org: BaseOrganization = BaseOrganization.get_by_id(self.organization_id)
            uuid.UUID(str(org.hubspot_refresh_token))
        except Exception as e:
            print(f"WARNING: HubspotClient cannot access refresh token {e}")

    # TODO(p2, devx): This is copy-pasted to upload_voice/app.py
    def authorize_from_code(self, organization_id: uuid.UUID, authorization_code: str):
        tokens = None
        try:
            tokens = self.api_client.auth.oauth.tokens_api.create(
                grant_type="authorization_code",
                redirect_uri=HUBSPOT_REDIRECT_URL,
                client_id=HUBSPOT_CLIENT_ID,
                client_secret=HUBSPOT_CLIENT_SECRET,
                # This is a one-time authorization code to get access and refresh tokens - so don't screw up.
                code=authorization_code,
            )
        except oauth.ApiException as e:
            print(f"ERROR: HubspotClient cannot create authorize with oauth {e}")

        org = BaseOrganization.get_by_id(organization_id)
        now = datetime.datetime.now()
        org.hubspot_linked_at = now
        org.hubspot_access_token = tokens.access_token
        try:
            uuid.UUID(str(tokens.refresh_token))
        except Exception as e:
            print(
                f"WARNING: expected refresh_token to be an UUID, got {type(tokens.refresh_token)}: {e}"
            )
        org.hubspot_refresh_token = tokens.refresh_token
        # We subtract 60 seconds to make more real.
        org.hubspot_expires_at = now + datetime.timedelta(
            seconds=tokens.expires_in - 60
        )
        org.save()

    # TODO(P0, bug): We have to somehow use the refresh token to get new access_tokens
    # https://legacydocs.hubspot.com/docs/methods/oauth2/oauth2-quickstart#refreshing-oauth-20-tokens
    # From Auth0 docs:
    # * While refresh tokens are often long-lived, the authorization server can invalidate them.
    # * Some of the reasons a refresh token may no longer be valid include:
    #   * the authorization server has revoked the refresh token
    #   * the user has revoked their consent for authorization
    #   * the refresh token has expired
    #   * the authentication policy for the resource has changed (e.g. it only wanted reads, but now it requires writes)
    def _ensure_token_fresh(self) -> ApiSingleResponse:
        if self.expires_at_cache is None:
            organization = BaseOrganization.get_by_id(self.organization_id)
            self.expires_at_cache = organization.hubspot_expires_at
            if bool(self.expires_at_cache):
                self.api_client.access_token = organization.hubspot_access_token
                print(
                    f"reusing cached access token valid until {self.expires_at_cache}"
                )

        now = datetime.datetime.now(pytz.UTC)
        if (
            self.expires_at_cache is None
            or self.expires_at_cache.astimezone(pytz.UTC) < now
        ):
            print(
                f"gonna refresh token for organization {self.organization_id} "
                f"cause expires at {self.expires_at_cache} and now is {now}"
            )
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
                # We subtract 300 seconds to make more real.
                organization.hubspot_expires_at = now + datetime.timedelta(
                    seconds=tokens.expires_in - 300
                )
                if (
                    bool(tokens.refresh_token)
                    and organization.hubspot_refresh_token != tokens.refresh_token
                ):
                    # TODO(P1, security): We cannot just store plaintext refresh tokens, use some 3rd party for that.
                    organization.hubspot_refresh_token = tokens.refresh_token
                    print(
                        f"refresh_token changed, updating and will be valid until {organization.hubspot_expires_at}"
                    )
                organization.save()

                self.expires_at_cache = organization.hubspot_expires_at
                self.api_client.access_token = organization.hubspot_access_token
                print(f"token refreshed, expires at {self.expires_at_cache}")
            except oauth.ApiException as e:
                print(f"ERROR when fetching access token: {e}")
                return self._handle_exception("oauth refresh", e)

        return ApiSingleResponse(200, None)

    def _handle_exception(
        self, endpoint: str, e: contacts.ApiException, request_body=None
    ) -> ApiSingleResponse:
        body = json.loads(e.body)
        msg = body.get("message", str(e))
        req = (
            f"request_body: {str(request_body)}"
            if bool(request_body)
            else "no request body"
        )
        hs_object_id = None
        if e.status == HTTPStatus.CONFLICT:
            match = re.search(r"Existing ID:\s*(\d+)", msg)
            if match:
                hs_object_id = int(match.group(1))
            # TODO(P1, reliability): Refetch object and return it

        print(
            f"ERROR Hubspot API call HTTP {e.status} for {endpoint} with {req}: {msg}"
        )
        return ApiSingleResponse(
            e.status, body.get("message", str(e)), hs_object_id=hs_object_id
        )

    # TODO(P1, devx): Refactor these functions into one as they almost the same
    def crm_contact_create(self, props) -> ApiSingleResponse:
        token_result = self._ensure_token_fresh()
        if token_result.status != 200:
            return token_result

        request_body = SimplePublicObjectInputForCreate(properties=props)
        try:
            api_response = self.api_client.crm.contacts.basic_api.create(
                simple_public_object_input_for_create=request_body
            )
            print(f"Contact created ({type(api_response)}): {api_response}")
            return ApiSingleResponse(HTTPStatus.OK, api_response)
        except contacts.ApiException as e:
            return self._handle_exception("contact create", e, request_body)

    def crm_contact_get_all(self):
        self._ensure_token_fresh()
        try:
            # Handles the pagination with default limit = 100
            return self.api_client.crm.contacts.get_all()
        except contacts.ApiException as e:
            return self._handle_exception("contact get_all", e)

    def crm_call_create(self, props) -> ApiSingleResponse:
        token_result = self._ensure_token_fresh()
        if token_result.status != 200:
            return token_result

        request_body = SimplePublicObjectInputForCreate(
            properties=props,
        )
        try:
            api_response = self.api_client.crm.objects.calls.basic_api.create(
                simple_public_object_input_for_create=request_body
            )
            print(f"Call created: {api_response}")
            return ApiSingleResponse(HTTPStatus.OK, api_response)
        except calls.ApiException as e:
            return self._handle_exception("call create", e, request_body)

    def crm_task_create(self, props) -> ApiSingleResponse:
        token_result = self._ensure_token_fresh()
        if token_result.status != 200:
            return token_result

        request_body = SimplePublicObjectInputForCreate(
            properties=props,
        )
        try:
            api_response = self.api_client.crm.objects.tasks.basic_api.create(
                simple_public_object_input_for_create=request_body
            )
            print(f"Task created: {api_response}")
            return ApiSingleResponse(HTTPStatus.OK, api_response)
        except tasks.ApiException as e:
            return self._handle_exception("create task", e, request_body)

    # https://community.hubspot.com/t5/APIs-Integrations/Creating-associations-in-hubspot-api-nodejs-new-version/td-p/803292
    # TODO(P1, devx): We can derive from_type and to_type from assoc_type
    def crm_association_create(
        self,
        from_type: str,
        from_id: int,
        to_type: str,
        to_id: int,
        assoc_type: AssociationType,
    ):
        if from_id is None:
            return None
        if to_id is None:
            return None
        # TODO(P1, reliability): Handle error without code failing
        self._ensure_token_fresh()
        api_response = self.api_client.crm.associations.v4.basic_api.create(
            object_type=from_type,
            object_id=from_id,
            to_object_type=to_type,
            to_object_id=to_id,
            association_spec=[
                AssociationSpec(
                    # ["HUBSPOT_DEFINED", "USER_DEFINED", "INTEGRATOR_DEFINED"]
                    association_category="HUBSPOT_DEFINED",
                    association_type_id=assoc_type.value,
                )
            ],
        )
        print(f"Association created: {api_response}")
        # Example: {from_object_type_id '0-1', to_object_type_id: '0-27' ... }
        return api_response

    def list_custom_properties(self, object_type="contact"):
        properties_api = self.api_client.crm.properties.core_api
        try:
            response = properties_api.get_all(object_type=object_type)
            # print(f"structure of list_custom_properties ({type(response).__name__}): {dir(response)}")
            return response
        except Exception as e:
            print(f"Exception when listing custom properties: {e}")
            return None

    def list_owners(self):
        try:
            response = self.api_client.crm.owners.get_all()
            print(f"list_owners returned: {response}")
            return response
        except Exception as e:
            print(f"Exception while listing all owners: {e}")
            return None
