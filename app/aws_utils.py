import os


DYNAMO_URL_PROD = "https://dynamodb.us-west-2.amazonaws.com"


def get_bucket_url(bucket: str, key: str):
    return f"https://{bucket}.s3.amazonaws.com/{key}"


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
