import datetime

import boto3
from botocore.exceptions import NoCredentialsError

s3 = boto3.client("s3")

ALLOWED_ORIGINS = ["https://app.voxana.ai", "http://localhost:3000"]


def lambda_handler(event, context):
    # Extract the source IP address
    source_ip = event["requestContext"]["identity"].get("sourceIp", "unknown")

    # Specify the S3 bucket and file name
    bucket_name = "requests-from-api-voxana"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    file_name = f"{source_ip}/{timestamp}"

    # Extract the origin from the request headers
    origin = event["headers"].get("origin", "unknown")

    # Set the allowed origin in the response to the origin of the request if it's in the list of allowed origins
    allowed_origin = origin if origin in ALLOWED_ORIGINS else "unknown"

    try:
        # Generate a presigned S3 PUT URL
        response = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket_name,
                "Key": file_name,
                "ContentType": "audio/webm",  # add this line
            },
            ExpiresIn=600,  # URL will be valid for 10 minutes
        )
    except NoCredentialsError:
        return {
            "statusCode": 401,
            "body": "Error generating presigned URL: No AWS Credentials",
            "headers": {
                "Access-Control-Allow-Origin": allowed_origin,
                "Access-Control-Allow-Credentials": True,
            },
        }

    # Return the presigned URL
    return {
        "statusCode": 200,
        "body": response,  # this is the presigned URL
        "headers": {
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Credentials": True,
        },
    }
