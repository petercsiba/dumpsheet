# TODO(P1, dumpsheet migration): Separate out this file into smaller FastAPI modules
import datetime
import os
import re
import uuid
from typing import Dict, Optional, Annotated, Union

import boto3
import peewee  # noqa
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, Header, HTTPException
from hubspot import HubSpot
from hubspot.auth import oauth
from pydantic import BaseModel, EmailStr
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import RedirectResponse

from common.aws_utils import get_bucket_url
from common.config import ENV, ENV_LOCAL, ENV_PROD, AWS_SECRET_ACCESS_KEY, AWS_ACCESS_KEY_ID, \
    POSTGRES_LOGIN_URL_FROM_ENV
# TODO(P2, dumpsheet migration): Instead of import the entire module, just import the classes.
from database import account, data_entry, models
from database.constants import (
    ACCOUNT_STATE_ACTIVE,
    ACCOUNT_STATE_MERGED,
    ACCOUNT_STATE_PENDING,
    DESTINATION_HUBSPOT_ID,
    OAUTH_DATA_TOKEN_TYPE_OAUTH,
    ORGANIZATION_ROLE_CONTRIBUTOR,
    ORGANIZATION_ROLE_OWNER,
)
from database.models import BaseDataEntry, BaseEmailLog
from database.oauth_data import OauthData
from database.organization import Organization
from database.pipeline import Pipeline
from supawee.client import connect_to_postgres_i_will_call_disconnect_i_promise, disconnect_from_postgres_as_i_promised

s3 = boto3.client("s3", aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

ALLOWED_ORIGINS = ["https://app.dumpsheet.com", "http://localhost:3000"]
HUBSPOT_APP_ID = "2150554"
HUBSPOT_CLIENT_ID = "501ffe58-5d49-47ff-b41f-627fccc28715"
HUBSPOT_REDIRECT_URL = "https://api.dumpsheet.com/hubspot/oauth/redirect"
TWILIO_FUNCTIONS_API_KEY = "twilio-functions-super-secret-key-123"


# ======= FAST API BOILERPLATE =======

app = FastAPI()
# app.include_router(hubspot_router)


origins = []
local_origins = [
    "http://localhost:3000",  # Adjust this if needed
    "http://localhost:8080",  # Your server's port
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
]
prod_origins = [
    "https://dumpsheet.com",
    "https://www.dumpsheet.com",
    "https://app.dumpsheet.com",
    "https://api.dumpsheet.com",
]
if ENV == ENV_LOCAL:
    print(
        "INFO: Adding CORS Middleware for LOCAL Environment (DO NOT DO IN PRODUCTION)"
    )
    origins = local_origins
elif ENV == ENV_PROD:
    print(
        "INFO: Adding CORS Middleware for PROD Environment"
    )
    origins = prod_origins + local_origins  # TODO(P1, yolo): Remove local_origins
else:
    raise Exception(f"Unknown environment {ENV} cannot start server")

# Apply CORS middleware
# TODO(P1, devx): It would be nice to add a correlation id https://github.com/snok/asgi-correlation-id
#   Actually, we can likely just use the fly-request-id header maybe (at least present on the response)
#   curl -I -X GET https://api.dumpsheet.com/
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # or use ["*"] to allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    postgres_login_url = POSTGRES_LOGIN_URL_FROM_ENV
    # with client.connect_to_postgres(postgres_login_url):
    # Indeed, in AWS Lambda, it is generally recommended not to explicitly close database connections
    # at the end of each function invocation. Lambda execution context will freeze and thaw it.
    connect_to_postgres_i_will_call_disconnect_i_promise(postgres_login_url)  # lies


@app.on_event("shutdown")
def shutdown():
    disconnect_from_postgres_as_i_promised()


# ======= API ENDPOINTS =======
@app.get("/")
def read_root():
    return {"status": "ok", "version": "1.0.0"}


class GetPresignedUrlResponse(BaseModel):
    presigned_url: str  # actually required, but we oftentimes mess up and that messes up return code to 500
    email: Optional[EmailStr] = None
    account_id: Optional[str] = None  # uuid really


@app.get("/upload/voice", response_model=GetPresignedUrlResponse)
async def get_presigned_url(request: Request, x_account_id: Annotated[Union[str, None], Header()] = None):
    # Specify the S3 bucket and file name
    bucket_name = "requests-from-api-voxana"
    data_entry_id = uuid.uuid4()
    file_name = f"{data_entry_id}.webm"
    print(f"received upload request for data entry {data_entry_id}: account_id {x_account_id}")
    # We should get this from the request
    content_type = "audio/webm"

    try:
        # Generate a presigned S3 PUT URL
        presigned_url = s3.generate_presigned_url(
            "put_object",
            # Ideally, we would include `data_entry_id` as Metadata.
            Params={
                "Bucket": bucket_name,
                "Key": file_name,
                "ContentType": content_type,  # add this line
            },
            ExpiresIn=600,  # URL will be valid for 10 minutes
        )
        print("presigned_url generated")
    except NoCredentialsError:
        # Officially HTTPException should only be used with 4xx
        raise HTTPException(500, "error generating presigned URL: No AWS Credentials")

    # NOTE: To allow extra headers you need to allow-list them in the CORS policy
    # https://chat.openai.com/share/4e0034b2-4012-4ef9-97dc-e41b66bec335
    if x_account_id and x_account_id != "null" and x_account_id != "undefined":
        print(f"Received account_id: {x_account_id} type {type(x_account_id)}")
        acc = account.Account.get_by_id(x_account_id)
    else:
        # TODO(P0, dumpsheet migration): This IP onboarding is just too custom, remove and just require X-Account-Id.
        # Extract some identifiers - these should NOT be use for auth - but good enough for a demo.
        source_ip = request.client.host
        user_agent = "this is deprecated in the future"
        print(f"Received source_ip: {source_ip} and user_agent {user_agent}")
        acc = account.Account.get_or_onboard_for_ip(
            ip_address=source_ip, user_agent=user_agent
        )

    if bool(acc.user):
        # TODO(P0, auth): Support authed sessions somehow.
        raise HTTPException(403, "please sign in")
    # We only want to collect the email address if not already associated with this IP address.
    email = acc.get_email()
    account_id = str(acc.id)  # maybe we should have a UUIDEncoder

    inserted = models.BaseDataEntry.insert(
        id=data_entry_id,
        account=acc,
        display_name=f"Voice recording upload from {(datetime.datetime.now().strftime('%B %d, %H:%M'))}",
        idempotency_id=data_entry_id,  # TODO(P1, ux): we can send a client-side recording idempotency id
        input_type=content_type,
        input_uri=get_bucket_url(bucket=bucket_name, key=file_name),
        state=data_entry.STATE_UPLOAD_INTENT
        # output_transcript, processed_at are None
    ).execute()
    print(f"inserted data entries {inserted}")
    return GetPresignedUrlResponse(presigned_url=presigned_url, email=email, account_id=account_id)


class PostUpdateEmailRequest(BaseModel):
    email: str
    account_id: str  # uuid really


class PostUpdateEmailResponse(BaseModel):
    detail: str


# curl -X POST -d '{email: "petherz+curl@gmail.com", account_id: "f11a156d-2dd1-44a4-83de-3dca117765b8"}' https://api.dumpsheet.com/upload/voice  # noqa
# TODO(P0, dumpsheet migration): This IP onboarding is just too custom use Supabase Auth or other off-shelf solution.
@app.post("/upload/voice", response_model=PostUpdateEmailResponse, status_code=200)
def post_update_email(request: PostUpdateEmailRequest):
    # TODO(P0, ux): Actually process terms of service from tos_accepted
    account_id = request.account_id
    email_raw = request.email

    if not email_raw or not account_id:
        raise HTTPException(400, "both email and account_id parameters are required")
    email = str(email_raw).lower()
    print(f"handle_post_request_for_update_email {email}:{account_id}")

    print(f"looking for account with id {account_id}")
    acc: account.Account = account.Account.get_or_none(account.Account.id == account_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    existing_email = acc.get_email()

    # so we can set it for its Onboarding object.
    onboarding = models.BaseOnboarding.get_or_none(models.BaseOnboarding.account == acc)
    if not bool(onboarding):
        raise HTTPException(404, "onboarding not found")

    # We want to be careful with this update as handling identities must be robust
    # 1. Check if such email already has an account (in theory there can be multiple onboardings for the same email)
    acc_for_email = account.Account.get_by_email_or_none(email)
    if bool(acc_for_email):
        print(f"Found existing account {acc_for_email.id} for email {email}")
        # However, if you want to indicate that the resource was already created prior to the request,
        # there isn't a specific HTTP status code for this situation.
        if str(acc_for_email.id) == str(account_id):
            return PostUpdateEmailResponse(detail="account already exists with the provided email")
        if bool(existing_email) and existing_email != email:
            raise HTTPException(
                409, "requested account is claimed by a different a email address"
            )
        new_account_id = acc_for_email.id
        try:
            # Different accounts, same email.
            # account.Account.merge_in(acc_for_email.id, account_id)
            onboarding.account_id = new_account_id
            onboarding.email = email
            onboarding.save()
            de_update_query = BaseDataEntry.update(account_id=new_account_id).where(
                BaseDataEntry.account_id == account_id
            )
            print(f"DataEntry update query: {de_update_query.sql}")
            num_de = de_update_query.execute()
            num_el = (
                BaseEmailLog.update(account_id=new_account_id)
                .where(BaseEmailLog.account_id == account_id)
                .execute()
            )
            acc.state = ACCOUNT_STATE_MERGED
            acc.merged_into_id = new_account_id
            acc.save()
            print(
                f"Updated 1 onboardings, {num_de} data entries and {num_el} email logs"
            )
            return PostUpdateEmailResponse(detail=f"account {account_id} merged into existing {new_account_id}")
        except Exception as e:
            raise HTTPException(
                500,
                f"could not merge accounts {account_id} -> {new_account_id} cause {e}",
            )

    # 2. Vice-versa, prevent overriding emails for existing acc by checking that account if already has claimed email
    if bool(existing_email):
        if existing_email != email:
            raise HTTPException(
                409, "requested account is claimed by a different a email address"
            )
        return PostUpdateEmailResponse(detail="account already exists with the provided email")

    # This means existing_account has NO associated User, AND the email is un-used,
    onboarding.email = email
    onboarding.save()
    if acc.state == ACCOUNT_STATE_PENDING:
        acc.state = ACCOUNT_STATE_ACTIVE
        acc.save()

    return PostUpdateEmailResponse(detail="account email updated")


class CallSetEmailRequest(BaseModel):
    phone_number: str
    message: str


class CallSetEmailResponse(BaseModel):
    detail: str


@app.post("/call/set-email", status_code=201, response_model=CallSetEmailResponse)
def call_set_email(request: CallSetEmailRequest):
    # TODO(P2, dumpsheet migration): This should be a separate endpoint for Twilio Functions
    # if api_key != TWILIO_FUNCTIONS_API_KEY:
    #    raise HTTPException(403, "x-api-key is required")

    phone_number = request.phone_number
    message = request.message
    print(f"received message from {phone_number}: {message}")
    if phone_number is None or message is None:
        raise HTTPException(400, "both phone_number and message are required params")

    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    match = re.search(pattern, message)
    new_email_raw = match.group(0) if match else None
    if new_email_raw is None:
        raise HTTPException(400, "no email address found in message")
    new_email = new_email_raw.lower()

    acc = account.Account.get_by_phone_or_none(phone_number)
    if acc is None:
        raise HTTPException(500, f"account should be already present for {phone_number}")

    existing_email = acc.get_email()
    if existing_email is None:
        existing_onboarding = models.BaseOnboarding.get(
            models.BaseOnboarding.account_id == acc.id
        )
        existing_onboarding.email = new_email
        print(f"updating existing onboarding for {phone_number} to {new_email}")
        existing_onboarding.save()
        return CallSetEmailResponse(detail="email updated")
    elif existing_email == new_email:
        # TODO(P2, devx): This should be a 200, but what is the FastAPI way for 200 vs 201?
        return HTTPException(200, "email already set")
    assert existing_email != new_email
    raise HTTPException(
        400,
        f"cannot reset email through this endpoint, phone_number claimed by {existing_email}",
    )


def _parse_account_id_from_state_param(param: Optional[str]) -> Optional[uuid.UUID]:
    if not bool(param):
        print("State parameter is missing")
        return None

    account_id = None
    account_id_key_value = param.split(":")
    if len(account_id_key_value) == 2 and account_id_key_value[0] == "accountId":
        account_id_str = account_id_key_value[1]
        try:
            account_id = uuid.UUID(
                account_id_str, version=4
            )  # Assuming it's a version 4 UUID
            print(f"Valid Account ID: {account_id}")
        except ValueError:
            print(f"Invalid UUID format for {account_id_str}")
    else:
        print(f"Invalid state parameter {param}")

    return account_id


@app.get("/hubspot/oauth/redirect", response_class=RedirectResponse, status_code=302)
def handle_get_request_for_hubspot_oauth_redirect(code: str, state: Optional[str]) -> str:
    print(f"HUBSPOT OAUTH REDIRECT EVENT: {code}")

    authorization_code = code
    client_secret = os.environ.get("HUBSPOT_CLIENT_SECRET")
    # TODO(p2, devx): We should move this into app.HubspotClient once our deployments are more consolidated.
    api_client = HubSpot()
    try:
        tokens = api_client.auth.oauth.tokens_api.create(
            grant_type="authorization_code",
            redirect_uri=HUBSPOT_REDIRECT_URL,
            client_id=HUBSPOT_CLIENT_ID,
            client_secret=client_secret,
            # This is a one-time authorization code to get access and refresh tokens - so don't screw up.
            code=authorization_code,
        )
    except oauth.ApiException as e:
        raise HTTPException(
            500, f"Exception when fetching access token from HubSpot: {e}"
        )
    api_client.access_token = tokens.access_token

    # We rather have multiple OauthData entries for the same refresh_token then trying to have a normalized structure.
    oauth_data_id = OauthData.insert(
        token_type=OAUTH_DATA_TOKEN_TYPE_OAUTH,
    ).execute()
    OauthData.update_safely(
        oauth_data_id=oauth_data_id,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )

    # == SECOND, we check all their accounts to see if they are part of any organization already
    # List[PublicOwner]
    owners_response = api_client.crm.owners.get_all()
    accounts = account.Account.get_or_onboard_for_hubspot(
        owners_response=owners_response
    )
    assert len(accounts) > 0

    accounts_with_no_org_id = []
    unique_org_ids = set()
    for acc in accounts:
        if acc.organization_id is None:
            accounts_with_no_org_id.append(acc)
        else:
            unique_org_ids.add(acc.organization_id)
    print(
        f"Success fetching Hubspot owners data, total count {len(accounts)} "
        f"from which accounts with no orgs {len(accounts_with_no_org_id)}"
    )

    if len(unique_org_ids) == 0:
        print("Org onboard: None of the Hubspot accounts have a organization")
    elif len(unique_org_ids) == 1:
        print(
            f"Org onboard: Found one organization among Hubspot accounts: {unique_org_ids}"
        )
    else:
        print(
            f"WARNING: Potential trouble linking HubSpot organization when accounts have multiple orgs {unique_org_ids}"
        )

    # == THIRD, we check through HubId if an organization already exists (as an idempotency_key).
    # AccessTokenInfoResponse
    org_metadata = api_client.auth.oauth.access_tokens_api.get(api_client.access_token)
    print(f"org_metadata={org_metadata}")
    external_org_id = org_metadata.hub_id
    external_org_admin_email = org_metadata.user
    external_org_name = org_metadata.hub_domain
    existing_pipeline = Pipeline.get_or_none_for_external_org_id(
        external_org_id, DESTINATION_HUBSPOT_ID
    )

    # == FOURTH, we check for the admin account if that has an organization or not
    # NOTE: admin_account_id can be None
    admin_account_id = _parse_account_id_from_state_param(state)
    if admin_account_id is None:
        print(
            f"Trying to get admin account for hubspot oauth linker {external_org_admin_email}"
        )
        admin_account = account.Account.get_by_email_or_none(external_org_admin_email)
        if bool(admin_account):
            admin_account_id = admin_account.id
    else:
        admin_account = account.Account.get_by_id(admin_account_id)

    # == AFTER all the prep work looking for idempotency_id we decide if create a new org or reuse an existing one
    if bool(admin_account) and bool(admin_account.organization_id):
        print(
            f"Org Decision: will be using organization of admin account {admin_account}"
        )
        org = admin_account.organization
    elif bool(existing_pipeline):
        print(
            f"Org Decision: will be using organization of the existing pipeline {existing_pipeline}"
        )
        org = existing_pipeline.organization
    else:
        print("Org Decision: creating a new org")
        org = Organization.get_or_create_for_account_id(
            admin_account_id, name=external_org_name
        )
    print(f"CHOSEN ORGANIZATION: {org}")

    # Update pipeline
    pipeline = Pipeline.get_or_create_for(
        external_org_id, org.id, DESTINATION_HUBSPOT_ID
    )
    # Here we deliberately allow to override the refresh_token, as we might need to re-auth time-to-time.
    if pipeline.oauth_data_id != oauth_data_id:
        od1 = OauthData.get_by_id(pipeline.oauth_data_id)
        od2 = OauthData.get_by_id(oauth_data_id)
        if od1.refresh_token != od2.refresh_token:
            print(
                f"WARNING: different refresh token given through oauth than in use for pipeline {pipeline.id}"
                f", check new oauth_data_id={oauth_data_id} and old {pipeline.oauth_data_id}"
            )
    pipeline.oauth_data_id = oauth_data_id
    print(f"setting pipeline.oauth_data_id to {oauth_data_id}")

    if pipeline.external_org_id is None:
        pipeline.external_org_id = org_metadata.hub_id
        print(f"setting pipeline.external_org_id to {pipeline.external_org_id}")
    pipeline.save()

    # Update org
    if org.name is None:
        print(f"setting org.name to {external_org_name}")
        org.name = external_org_name
    org.save()

    # Update account
    # TODO(P2, devx): Feels like Account<->Organization should have a link object to - with metadata.
    #   Or it something feels off of having both Organization and Pipeline.
    for acc in accounts:
        if acc.organization_id is None:
            acc.organization_id = org.id
        elif acc.organization_id != org.id:
            print(f"WARNING: account part of another organization {acc}")
        if acc.organization_role is None:  # to not over-write an "owner"
            acc.organization_role = (
                ORGANIZATION_ROLE_OWNER
                if acc.id == admin_account_id
                else ORGANIZATION_ROLE_CONTRIBUTOR
            )
        acc.save()

    return f"https://app.dumpsheet.com?hubspot_status=success&account_id={admin_account_id}"
