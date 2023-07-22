import datetime
import random

import boto3
from botocore.exceptions import NoCredentialsError

# Lambda extracts the layer contents into the /opt directory
# in the function execution environment.
# Lambda extracts the layers in the order that you added them to the function.
# import sys
# sys.path.insert(0, "/opt")
from database import account, client, models

s3 = boto3.client("s3")

ALLOWED_ORIGINS = ["https://app.voxana.ai", "http://localhost:3000"]


def get_bucket_url(bucket_name, key):
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

    try:
        # Generate a presigned S3 PUT URL
        response = s3.generate_presigned_url(
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

    with client.connect_to_postgres():
        # Add referer, utm_source, user_agent here
        # https://chat.openai.com/share/b866f3da-145c-4c48-8a34-53cf85a7eb19
        acc = account.Account.get_or_onboard_for_ip(ip_address=source_ip)
        r = str(random.randint(0, 99)).zfill(2)
        # Works for API Gateway
        request_id = event["requestContext"]["requestId"]

        models.BaseDataEntry.insert(
            account=acc,
            display_name=f"friendly-cat-{r}",  # reference_key
            idempotency_id=request_id,
            input_type=content_type,
            input_uri=get_bucket_url(bucket_name=bucket_name, key=file_name),
            # output_transcript, processed_at are None
        )

    # Return the presigned URL
    return {
        "statusCode": 200,
        "body": response,  # this is the presigned URL
        "headers": {
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Credentials": True,
        },
    }
