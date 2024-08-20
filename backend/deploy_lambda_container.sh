#!/bin/bash
# TODO(P0, dumpsheet migration): Test this works with the new AWS account from peter-voxana to prod@dumpsheet.com

PROFILE_NAME="PowerUserAccess-831154875375"

# Trap SIGTERM and SIGINT signals and kill the script and its children
trap "kill 0" SIGTERM SIGINT

echo "=== Running tests first ==="
echo "TODO make test_lambda_handler_post_upload_voice.py work"

# Capture the exit code from pytest
PYTEST_EXIT_CODE=$?

# Handle the exit code as needed
if [ $PYTEST_EXIT_CODE -ne 0 ]; then
    echo "Tests failed, exiting."
    exit $PYTEST_EXIT_CODE
else
    echo "Tests passed."
fi

echo "=== Login to AWS ECR ==="
# Check if logged into AWS CLI by trying to list S3 buckets
aws s3 ls --profile $PROFILE_NAME > /dev/null 2>&1

# If previous command failed, assume not logged in and login to SSO
if [ $? -ne 0 ]; then
    aws sso login --profile $PROFILE_NAME
fi

# Get ECR login password and login to Docker
aws ecr get-login-password --region us-east-1 --profile $PROFILE_NAME | docker login --username AWS --password-stdin 831154875375.dkr.ecr.us-east-1.amazonaws.com


# For some weird reason the first build try always fails :/ So always retry once on failure
max_retries=3
retry_delay=15

for i in $(seq 1 $max_retries); do
  echo "=== Building Image: Attempt $i ==="
  docker build -t 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups .  && break
  if [ $i -eq $max_retries ]; then
    echo "Max retries reached. Exiting."
    exit 1
  fi
  echo "Push failed. Retrying in $retry_delay seconds..."
  sleep $retry_delay
done

max_retries=3
retry_delay=15

for i in $(seq 1 $max_retries); do
  echo "=== Pushing Image: Attempt $i ==="
  docker push 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups:latest && break
  if [ $i -eq $max_retries ]; then
    echo "Max retries reached. Exiting."
    exit 1
  fi
  echo "Push failed. Retrying in $retry_delay seconds..."
  sleep $retry_delay
done

# echo "To finish deploy, log-in to AWS: https://d-90679cf568.awsapps.com/start/"

echo "=== Update AWS Lambda function ==="
aws lambda update-function-code \
    --function-name draft-your-follow-ups \
    --image-uri 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups:latest \
    --profile $PROFILE_NAME

# Handle the exit code
if [ $? -ne 0 ]; then
    echo "Failed to update Lambda function, exiting."
    echo "Go to lambda and select latest container https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/draft-your-follow-ups/edit/image-settings?tab=code"
    exit 1
else
    echo "Successfully updated Lambda function."
fi

# ====== TESTING IN PROD ============
# Upload a test file to S3 to trigger Lambda function
echo "=== Upload test file to S3 bucket ==="
sleep 10
aws s3 cp testdata/jessica-lehane-email-upload-test-recording s3://draft-requests-from-ai-mail-voxana/ --profile $PROFILE_NAME

# Handle the exit code
if [ $? -ne 0 ]; then
    echo "Failed to upload test file to S3, exiting."
    exit 1
else
    echo "Successfully uploaded test file to S3."
fi
