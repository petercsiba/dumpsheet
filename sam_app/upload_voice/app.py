# TODO(P0, devx): Migrate this to Flask, the AWS SAM for lambdas is just crazy shit show.
#  -- This script evolved into essentially an onboarding server endpoint.
import datetime
import json
import os
import re
import uuid
from typing import Dict, Optional

import boto3
import peewee  # noqa
from botocore.exceptions import NoCredentialsError
from hubspot import HubSpot
from hubspot.auth import oauth

# NOTE: There are a few copies of the "database" module around this repo.
# for IDE, doing ".database" would point to "backend/sam_app/upload_voice/database".
# Ideally, we would set up an AWS Lambda Layer, but I failed to achieve this.
from database import account, data_entry, models
from database.client import connect_to_postgres_i_will_call_disconnect_i_promise
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

s3 = boto3.client("s3")

ALLOWED_ORIGINS = ["https://app.voxana.ai", "http://localhost:3000"]
HUBSPOT_APP_ID = "2150554"
HUBSPOT_CLIENT_ID = "501ffe58-5d49-47ff-b41f-627fccc28715"
HUBSPOT_REDIRECT_URL = "https://api.voxana.ai/hubspot/oauth/redirect"
TWILIO_FUNCTIONS_API_KEY = "twilio-functions-super-secret-key-123"

# AWS Lambda Execution Context feature - this should save about 1 second on subsequent invocations.
secrets_cache = {}


# TODO(P1, devx): Replace with Doppler - AWS secret manager is also kinda crap to manage.
def get_secret(secret_id, env_var_name):
    if secret_id in secrets_cache:
        print(f"Using cached secret for {secret_id}")
        return secrets_cache[secret_id]

    try:
        # Try to get secret from environment variable
        secret = os.environ.get(env_var_name)
        if secret is not None:
            print(f"Using environment secret {env_var_name} for {secret_id}")
            return secret
    except KeyError:
        pass

    # If not found in environment or cache, fetch from Secrets Manager
    session = boto3.session.Session()
    secretsmanager_client = session.client(
        service_name="secretsmanager", region_name="us-east-1"
    )

    get_secret_value_response = secretsmanager_client.get_secret_value(
        SecretId=secret_id
    )

    print(f"Using secrets manager for secret {secret_id}")

    if "SecretString" in get_secret_value_response:
        secret = get_secret_value_response["SecretString"]
        # Cache the retrieved secret for future use
        secrets_cache[secret_id] = secret
    else:
        raise ValueError(f"Secret not found (or no perms) for {secret_id}")

    return secret


def get_bucket_url(bucket_name, key):
    # TODO(p3): We should try un-comment this
    # This might need urllib3 - kinda annoying dealing with Lambda deps.
    # location = s3.get_bucket_location(Bucket=bucket_name)['LocationConstraint']
    # if location is None:
    location = "us-east-1"  # default location (TODO: use some AWS_REGION env variable)
    bucket_url = f"https://{bucket_name}.s3.{location}.amazonaws.com/{key}"
    return bucket_url


def craft_response(
    status_code: int, body: Dict, headers: Optional[Dict] = None
) -> Dict:
    result = {"statusCode": status_code, "body": json.dumps(body)}
    if bool(headers):
        result["headers"] = headers
    return result


# NOTE: Please keep the `error_message` brief - do not include ids/values - to mitigate potential malicious action.
# If you need more info to debug, you can always log it.
def craft_error(status_code: int, error_message) -> Dict:
    print(f"ERROR({status_code}): {error_message}")
    return craft_response(status_code, {"error": error_message})


def craft_info(status_code: int, info_message) -> Dict:
    print(f"INFO({status_code}): {info_message}")
    return craft_response(status_code, {"info": info_message})


def format_user_agent(user_agent_str: str):
    s = re.sub(r"[ /_]", "-", user_agent_str)
    return re.sub(r"[^a-zA-Z0-9-.]", "", s)


def handle_get_request_for_presigned_url(event) -> Dict:
    # Specify the S3 bucket and file name
    bucket_name = "requests-from-api-voxana"
    data_entry_id = uuid.uuid4()
    file_name = f"{data_entry_id}.webm"
    print(f"received upload request for data entry {data_entry_id}: event {event}")
    # We should get this from the request
    content_type = "audio/webm"

    response = {}
    try:
        # Generate a presigned S3 PUT URL
        response["presigned_url"] = s3.generate_presigned_url(
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
        return craft_error(500, "error generating presigned URL: No AWS Credentials")

    # NOTE: To allow extra headers you need to allow-list them in the CORS policy
    # https://chat.openai.com/share/4e0034b2-4012-4ef9-97dc-e41b66bec335
    account_id = event["headers"].get("X-Account-Id", None)
    if account_id:
        print(f"Received account_id: {account_id}")
        acc = account.Account.get_by_id(account_id)
    else:
        # Extract some identifiers - these should NOT be use for auth - but good enough for a demo.
        source_ip = event["requestContext"]["identity"].get("sourceIp", "unknown")
        user_agent = format_user_agent(
            event["requestContext"]["identity"].get("userAgent", "")
        )
        anonymous_identifier = f"{source_ip}-{user_agent}"
        # Add referer, utm_source, user_agent here
        # https://chat.openai.com/share/b866f3da-145c-4c48-8a34-53cf85a7eb19
        acc = account.Account.get_or_onboard_for_ip(ip_address=anonymous_identifier)

    if bool(acc.user):
        # TODO(P0, auth): Support authed sessions somehow.
        return craft_error(401, "please sign in")
    # Works for API Gateway
    request_id = event["requestContext"]["requestId"]
    # We only want to collect the email address if not already associated with this IP address.
    response["email"] = acc.get_email()
    response["account_id"] = str(acc.id)  # maybe we should have a UUIDEncoder

    inserted = models.BaseDataEntry.insert(
        id=data_entry_id,
        account=acc,
        display_name=f"Voice recording upload from {(datetime.datetime.now().strftime('%B %d, %H:%M'))}",
        idempotency_id=request_id,
        input_type=content_type,
        input_uri=get_bucket_url(bucket_name=bucket_name, key=file_name),
        state=data_entry.STATE_UPLOAD_INTENT
        # output_transcript, processed_at are None
    ).execute()
    print(f"inserted data entries {inserted}")
    return craft_response(201, response)


# curl -X POST -d '{email: "petherz+curl@gmail.com", account_id: "f11a156d-2dd1-44a4-83de-3dca117765b8"}' https://api.voxana.ai/upload/voice  # noqa
def handle_post_request_for_update_email(event: Dict) -> Dict:
    body = json.loads(event["body"])
    email_raw = body.get("email")
    account_id = body.get("account_id")

    if not email_raw or not account_id:
        return craft_error(400, "both email and account_id parameters are required")
    email = str(email_raw).lower()
    print(f"handle_post_request_for_update_email {email}:{account_id}")

    print(f"looking for account with id {account_id}")
    acc: account.Account = account.Account.get_or_none(account.Account.id == account_id)
    if acc is None:
        return craft_error(404, "account not found")
    existing_email = acc.get_email()

    # so we can set it for its Onboarding object.
    onboarding = models.BaseOnboarding.get_or_none(models.BaseOnboarding.account == acc)
    if not bool(onboarding):
        return craft_error(404, "onboarding not found")

    # We want to be careful with this update as handling identities must be robust
    # 1. Check if such email already has an account (in theory there can be multiple onboardings for the same email)
    acc_for_email = account.Account.get_by_email_or_none(email)
    if bool(acc_for_email):
        # However, if you want to indicate that the resource was already created prior to the request,
        # there isn't a specific HTTP status code for this situation.
        if acc_for_email.id == account_id:
            return craft_info(200, "account already exists with the provided email")
        if bool(existing_email) and existing_email != email:
            return craft_error(
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
            return craft_info(
                200, f"account {account_id} merged into existing {new_account_id}"
            )
        except Exception as e:
            return craft_error(
                500,
                f"could not merge accounts {account_id} -> {new_account_id} cause {e}",
            )

    # 2. Vice-versa, prevent overriding emails for existing acc by checking that account if already has claimed email
    if bool(existing_email):
        if existing_email != email:
            return craft_error(
                409, "requested account is claimed by a different a email address"
            )
        return craft_info(200, "account already exists with the provided email")

    # This means existing_account has NO associated User, AND the email is un-used,
    onboarding.email = email
    onboarding.save()
    if acc.state == ACCOUNT_STATE_PENDING:
        acc.state = ACCOUNT_STATE_ACTIVE
        acc.save()

    return craft_info(200, "account email updated")


def handle_post_request_for_call_set_email(event):
    body = json.loads(event["body"])
    phone_number = body.get("phone_number")
    message = body.get("message")
    print(f"received message from {phone_number}: {message}")
    if phone_number is None or message is None:
        return craft_error(400, "both phone_number and message are required params")

    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    match = re.search(pattern, message)
    new_email_raw = match.group(0) if match else None
    if new_email_raw is None:
        return craft_error(400, "no email address found in message")
    new_email = new_email_raw.lower()

    acc = account.Account.get_by_phone_or_none(phone_number)
    if acc is None:
        return craft_error(500, f"account should be already present for {phone_number}")

    existing_email = acc.get_email()
    if existing_email is None:
        existing_onboarding = models.BaseOnboarding.get(
            models.BaseOnboarding.account_id == acc.id
        )
        existing_onboarding.email = new_email
        print(f"updating existing onboarding for {phone_number} to {new_email}")
        existing_onboarding.save()
        return craft_info(201, "email updated")
    elif existing_email == new_email:
        return craft_info(200, "email already set")
    assert existing_email != new_email
    return craft_error(
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


def handle_get_request_for_hubspot_oauth_redirect(event: Dict) -> Dict:
    print(f"HUBSPOT OAUTH REDIRECT EVENT: {event}")

    # == FIRST, we deal with the OAUTH stuff.
    authorization_code = event["queryStringParameters"].get("code", "")
    if not authorization_code:
        craft_error(400, "Missing authorization code")

    client_secret = get_secret(
        "arn:aws:secretsmanager:us-east-1:831154875375:secret:prod/hubspot/client_secret-ApsPp3",
        "HUBSPOT_CLIENT_SECRET",
    )
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
        return craft_error(
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
    external_org_id = org_metadata.hub_id
    external_org_admin_email = org_metadata.user
    external_org_name = org_metadata.hub_domain
    existing_pipeline = Pipeline.get_or_none_for_external_org_id(
        external_org_id, DESTINATION_HUBSPOT_ID
    )

    # == FOURTH, we check for the admin account if that has an organization or not
    # NOTE: admin_account_id can be None
    admin_account_id = _parse_account_id_from_state_param(
        event["queryStringParameters"].get("state", None)
    )
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
    pipeline.oauth_data_id = oauth_data_id
    if pipeline.external_org_id is None:
        pipeline.external_org_id = org_metadata.hub_id
        print(f"setting pipeline.external_org_id to {pipeline.external_org_id}")
    pipeline.save()

    # Update org
    if org.name is None:
        print(f"setting org.name to {external_org_name}")
        org.name = external_org_name
    if org.owner_account_id is None:
        print(f"setting org owner to {admin_account_id}")
        org.owner_account_id = admin_account_id
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

    return craft_response(
        302,
        body={
            "info": f"Hubspot Connected to organization {pipeline.organization_id}. Redirecting to app.voxana.ai ..."
        },
        headers={
            "Location": f"https://app.voxana.ai?hubspot_status=success&account_id={admin_account_id}"
        },
    )


# TODO(P1, Peter): Migrate this to a Flask / Django server - this lambda deployment is slowly starting to be ridiculous
# wtf sam
ENDPOINT_VOICE_UPLOAD = "/upload/voice"
ENDPOINT_CALL_SET_EMAIL = "/call/set-email"
ENDPOINT_HUBSPOT_OAUTH_REDIRECT = "/hubspot/oauth/redirect"


def lambda_handler(event, context):
    # https://docs.aws.amazon.com/lambda/latest/dg/services-apigateway.html#apigateway-example-event
    http_method = event["httpMethod"]
    api_endpoint = event["requestContext"][
        "resourcePath"
    ]  # event['path'] might work as well
    api_key = event["headers"].get("x-api-key")

    print(f"handling {http_method} {api_endpoint} request")

    # TODO(P1, security): This should be better, but PITA to use SAM for this.
    if api_endpoint == ENDPOINT_CALL_SET_EMAIL:
        if api_key != TWILIO_FUNCTIONS_API_KEY:
            return craft_error(403, "x-api-key is required")

    postgres_login_url = get_secret(
        secret_id="arn:aws:secretsmanager:us-east-1:831154875375:secret:prod/supabase/postgres_login_url-AvIn1c",
        env_var_name="POSTGRES_LOGIN_URL_FROM_ENV",
    )
    # with client.connect_to_postgres(postgres_login_url):
    # Indeed, in AWS Lambda, it is generally recommended not to explicitly close database connections
    # at the end of each function invocation. Lambda execution context will freeze and thaw it.
    connect_to_postgres_i_will_call_disconnect_i_promise(postgres_login_url)  # lies

    if api_endpoint == ENDPOINT_VOICE_UPLOAD:
        if http_method == "OPTIONS":
            # AWS API Gateway requires a non-empty response body for OPTIONS requests
            response = craft_response(200, {})
        elif http_method == "GET":
            response = handle_get_request_for_presigned_url(event)
        elif http_method == "POST":
            response = handle_post_request_for_update_email(event)
        else:
            raise ValueError(f"Invalid HTTP method: {http_method}")
    elif api_endpoint == ENDPOINT_CALL_SET_EMAIL:
        if http_method == "POST":
            response = handle_post_request_for_call_set_email(event)
        else:
            raise ValueError(f"Invalid HTTP method: {http_method}")
    elif api_endpoint == ENDPOINT_HUBSPOT_OAUTH_REDIRECT:
        if http_method == "GET":
            response = handle_get_request_for_hubspot_oauth_redirect(event)
        else:
            raise ValueError(f"Invalid HTTP method: {http_method}")
    else:
        raise NotImplementedError(api_endpoint)

    if "headers" not in response or response["headers"] is None:
        response["headers"] = {}

    # Add the CORS stuff here, as I couldn't figure out it in template.yaml nor API Gateway conf.
    # Extract the origin from the request headers
    origin = event["headers"].get("origin", "unknown")

    # Set the allowed origin in the response to the origin of the request if it's in the list of allowed origins
    # Some callers like twilio-functions don't need CORS.
    allowed_origin = origin if origin in ALLOWED_ORIGINS else "unknown"

    response["headers"]["Access-Control-Allow-Credentials"] = True
    response["headers"]["Access-Control-Allow-Origin"] = allowed_origin
    # Rest of them mostly for OPTIONS
    response["headers"]["Access-Control-Allow-Headers"] = "Content-Type,x-account-id"
    response["headers"]["Access-Control-Allow-Methods"] = "GET,POST"

    print(f"response: {response}")
    return response
