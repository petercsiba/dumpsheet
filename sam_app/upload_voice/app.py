import datetime
import json
import os
from typing import Dict

import boto3
import peewee  # noqa
from botocore.exceptions import NoCredentialsError

# Lambda extracts the layer contents into the /opt directory
# in the function execution environment.
# Lambda extracts the layers in the order that you added them to the function.
# import sys
# sys.path.insert(0, "/opt")
# NOTE: There are a few copies of the "database" module around this repo.
# for IDE, doing ".database" would point to "backend/sam_app/upload_voice/database",
# while "database" points to "backend/database".
from database import account, data_entry, models
from database.client import connect_to_postgres_i_will_call_disconnect_i_promise

s3 = boto3.client("s3")

ALLOWED_ORIGINS = ["https://app.voxana.ai", "http://localhost:3000"]

# AWS Lambda Execution Context feature - this should save about 1 second on subsequent invocations.
secrets_cache = {}


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


def craft_response(status_code: int, body: Dict) -> Dict:
    return {"statusCode": status_code, "body": json.dumps(body)}


# NOTE: Please keep the `error_message` brief - do not include ids/values - to mitigate potential malicious action.
# If you need more info to debug, you can always log it.
def craft_error(status_code: int, error_message) -> Dict:
    print(f"ERROR({status_code}): {error_message}")
    return craft_response(status_code, {"error": error_message})


def craft_info(status_code: int, info_message) -> Dict:
    print(f"INFO({status_code}): {info_message}")
    return craft_response(status_code, {"info": info_message})


def handle_get_request_for_presigned_url(event) -> Dict:
    # Extract the source IP address
    source_ip = event["requestContext"]["identity"].get("sourceIp", "unknown")

    # Specify the S3 bucket and file name
    bucket_name = "requests-from-api-voxana"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    file_name = f"{source_ip}/{timestamp}"
    print(
        f"received request from {source_ip} generating upload permissions for {file_name}"
    )
    # We should get this from the request
    content_type = "audio/webm"

    response = {}
    try:
        # Generate a presigned S3 PUT URL
        response["presigned_url"] = s3.generate_presigned_url(
            "put_object",
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

    # Add referer, utm_source, user_agent here
    # https://chat.openai.com/share/b866f3da-145c-4c48-8a34-53cf85a7eb19
    acc = account.Account.get_or_onboard_for_ip(ip_address=source_ip)
    # Works for API Gateway
    request_id = event["requestContext"]["requestId"]
    # We only want to collect the email address if not already associated with this IP address.
    response["email"] = acc.get_email()
    response["account_id"] = str(acc.id)  # maybe we should have a UUIDEncoder

    inserted = models.BaseDataEntry.insert(
        account=acc,
        display_name=f"Voice recording from {(datetime.datetime.now().strftime('%B %d, %H:%M'))}",
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
    email = body.get("email")
    account_id = body.get("account_id")

    if not email or not account_id:
        return craft_error(400, "both email and account_id parameters are required")
    print(f"handle_post_request_for_update_email {email}:{account_id}")

    # We want to be careful with this update as handling identities must be robust
    # 1. Check if such email already exists
    email_used_for = account.Account.get_by_email_or_none(email)
    if bool(email_used_for):
        # However, if you want to indicate that the resource was already created prior to the request,
        # there isn't a specific HTTP status code for this situation.
        if email_used_for.id != account_id:
            msg = f"account for {email} already exists"
            return craft_error(409, msg)
        return craft_info(200, "account already exists for the provided email")

    # 2. Vice-versa, check that account if already has claimed email
    print(f"looking for account with id {account_id}")
    existing_account = account.Account.get_or_none(account.Account.id == account_id)
    if existing_account is None:
        return craft_error(404, "account not found")

    existing_email = existing_account.get_email()
    if bool(existing_email):
        if existing_email != email:
            return craft_error(409, "account already claimed")
        return craft_info(200, "account already exists")

    # This means existing_account has NO associated User, and we can set it for its Onboarding object.
    existing_onboarding = existing_account.onboarding
    existing_onboarding.email = email
    existing_onboarding.save()
    return craft_info(200, "account email updated")


def lambda_handler(event, context):
    http_method = event["httpMethod"]
    print(f"handling {http_method} request")

    postgres_login_url = get_secret(
        secret_id="arn:aws:secretsmanager:us-east-1:831154875375:secret:prod/supabase/postgres_login_url-AvIn1c",
        env_var_name="POSTGRES_LOGIN_URL_FROM_ENV",
    )
    # with client.connect_to_postgres(postgres_login_url):
    # Indeed, in AWS Lambda, it is generally recommended not to explicitly close database connections
    # at the end of each function invocation. Lambda execution context will freeze and thaw it.
    connect_to_postgres_i_will_call_disconnect_i_promise(postgres_login_url)  # lies

    if http_method == "OPTIONS":
        # AWS API Gateway requires a non-empty response body for OPTIONS requests
        response = craft_response(200, {})
    elif http_method == "GET":
        response = handle_get_request_for_presigned_url(event)
    elif http_method == "POST":
        response = handle_post_request_for_update_email(event)
    else:
        raise ValueError(f"Invalid HTTP method: {http_method}")

    # Add the CORS stuff here, as I couldn't figure out it in template.yaml nor API Gateway conf.
    # Extract the origin from the request headers
    origin = event["headers"].get("origin", "unknown")

    # Set the allowed origin in the response to the origin of the request if it's in the list of allowed origins
    allowed_origin = origin if origin in ALLOWED_ORIGINS else "unknown"
    response["headers"] = {
        "Access-Control-Allow-Credentials": True,
        "Access-Control-Allow-Headers": "Content-Type",  # mostly for OPTIONS
        "Access-Control-Allow-Methods": "GET,POST",  # mostly for OPTIONS
        "Access-Control-Allow-Origin": allowed_origin,
    }
    return response
