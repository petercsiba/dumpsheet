import datetime
import json
import os

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
from database import account, client, data_entry, models

s3 = boto3.client("s3")

ALLOWED_ORIGINS = ["https://app.voxana.ai", "http://localhost:3000"]


def get_secret(secret_id, env_var_name):
    try:
        # Try to get secret from environment variable
        print(f"Using {env_var_name} for secret")
        secret = os.environ[env_var_name]
    except KeyError:
        # If not found in environment, fetch from Secrets Manager
        session = boto3.session.Session()
        secretsmanager_client = session.client(
            service_name="secretsmanager", region_name="us-east-1"
        )

        get_secret_value_response = secretsmanager_client.get_secret_value(
            SecretId=secret_id
        )

        if "SecretString" in get_secret_value_response:
            secret = get_secret_value_response["SecretString"]
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


def lambda_handler(event, context):
    # Extract the source IP address
    source_ip = event["requestContext"]["identity"].get("sourceIp", "unknown")

    # Specify the S3 bucket and file name
    bucket_name = "requests-from-api-voxana"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    file_name = f"{source_ip}/{timestamp}"
    print(
        f"received request from {source_ip} generating upload permissions for {file_name}"
    )

    # Extract the origin from the request headers
    origin = event["headers"].get("origin", "unknown")

    # Set the allowed origin in the response to the origin of the request if it's in the list of allowed origins
    allowed_origin = origin if origin in ALLOWED_ORIGINS else "unknown"
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
        return {
            "statusCode": 401,
            "body": "Error generating presigned URL: No AWS Credentials",
            "headers": {
                "Access-Control-Allow-Origin": allowed_origin,
                "Access-Control-Allow-Credentials": True,
            },
        }

    postgres_login_url = get_secret(
        secret_id="arn:aws:secretsmanager:us-east-1:831154875375:secret:prod/supabase/postgres_login_url-AvIn1c",
        env_var_name="POSTGRES_LOGIN_URL_FROM_ENV",
    )
    with client.connect_to_postgres(postgres_login_url):
        # Add referer, utm_source, user_agent here
        # https://chat.openai.com/share/b866f3da-145c-4c48-8a34-53cf85a7eb19
        acc, is_new = account.Account.get_or_onboard_for_ip(ip_address=source_ip)
        # Works for API Gateway
        request_id = event["requestContext"]["requestId"]
        # We only want to collect the email address if not already associated with this IP address.
        response["email"] = acc.get_email()
        response["account_id"] = str(acc.id)  # maybe we should have a UUIDEncoder

        models.BaseDataEntry.insert(
            account=acc,
            # display_name=f"friendly-cat-{r}",  # reference_key
            idempotency_id=request_id,
            input_type=content_type,
            input_uri=get_bucket_url(bucket_name=bucket_name, key=file_name),
            state=data_entry.STATE_UPLOAD_INTENT
            # output_transcript, processed_at are None
        )

    return {
        "statusCode": 200,
        "body": json.dumps(response),
        "headers": {
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Credentials": True,
        },
    }
