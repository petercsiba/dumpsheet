#!/bin/bash
# TODO(P0, devx): Migrate this SAM crap to some regular Python server on ECS / EC2

PROFILE_NAME="AdministratorAccess-831154875375"

# Trap SIGTERM and SIGINT signals and kill the script and its children
trap "kill 0" SIGTERM SIGINT

echo "=== Running tests first ==="
python -m pytest sam_app/tests/unit -v

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
aws s3 ls --profile $PROFILE_NAME > /dev/null 2>&1

# If previous command failed, assume not logged in and login to SSO
if [ $? -ne 0 ]; then
    echo "logging in"
    aws sso login --profile $PROFILE_NAME
fi

echo "=== BUILDING ==="
echo "copy new models (including the post-generate modified ones)"
cp -r database/ sam_app/upload_voice/database/

# Cause the (many) limitations of SAM, we have to run it in the root ( --template doesn't help)
echo "cd sam_app"
cd sam_app || exit

echo "build the sam stuff (otherwise it could omitted changes to app.py)"
sam build

# NOTE: Sometimes it fails to detect changes, you might need to clear the cache in:
# Locally: rm -rf .aws-sam/
# Remotely: https://s3.console.aws.amazon.com/s3/buckets/aws-sam-cli-managed-default-samclisourcebucket-ul50z4hzdzd9?region=us-east-1&tab=objects
echo "=== DEPLOYING ==="
yes | sam deploy --profile $PROFILE_NAME --parameter-overrides "DummyParam=$(date +%s)"

echo "curl the endpoint as test"
curl -X GET -H "X-Account-Id: 3776ef1f-23a0-43e8-b275-ba45e5af9dea" https://api.voxana.ai/upload/voice

cd ..
