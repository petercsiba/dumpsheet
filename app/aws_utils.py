import boto3
import os


DEFAULT_REGION = "us-west-2"
DYNAMO_URL_PROD = f"https://dynamodb.{DEFAULT_REGION}.amazonaws.com"


def get_boto_s3_client():
    return boto3.client('s3', region_name='us-west-2')


def get_bucket_url(bucket: str, key: str):
    # TODO(P2, robustness): Should we use quote here?
    return f"https://{bucket}.s3.{DEFAULT_REGION}.amazonaws.com/{key}"


def is_running_in_aws():
    if 'AWS_LAMBDA_FUNCTION_NAME' in os.environ:
        # Running in AWS Lambda
        return True

    if 'AWS_EXECUTION_ENV' in os.environ and 'AWS' in os.environ['AWS_EXECUTION_ENV']:
        # Running in an AWS environment (e.g., EC2, ECS, AWS Batch)
        return True

    return False


def get_dynamo_endpoint_url(port=8000):
    if is_running_in_aws():
        return DYNAMO_URL_PROD
    else:
        return f"http://localhost:{port}"
