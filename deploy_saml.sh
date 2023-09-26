#!/bin/bash
# TODO(P0, devx): Migrate this SAM crap to some regular Python server on ECS / EC2
#

# TEMPLATE_FILE=sam_app/template.yaml
PROFILE_NAME="AdministratorAccess-831154875375"

# Exit early when any step fails (like pytest fails)
set -e

echo "running tests"
python -m pytest sam_app/tests/unit -v

echo "copy new models (including the post-generate modified ones)"
cp -r database/ sam_app/upload_voice/database/fdsf

# Cause the (many) limitations of SAM, we have to run it in the root ( --template doesn't help)
echo "cd sam_app"
cd sam_app

echo "build the sam stuff (otherwise it could omitted changes to app.py)"
sam build

echo "deploy it"

# Check if logged into AWS CLI by trying to list S3 buckets
aws s3 ls --profile $PROFILE_NAME > /dev/null 2>&1
if [ $? -ne 0 ]; then
    aws sso login --profile $PROFILE_NAME
fi

# NOTE: Sometimes it fails to detect changes, you might need to clear the cache in:
# Locally: rm -rf .aws-sam/
# Remotely: https://s3.console.aws.amazon.com/s3/buckets/aws-sam-cli-managed-default-samclisourcebucket-ul50z4hzdzd9?region=us-east-1&tab=objects
yes | sam deploy --profile $PROFILE_NAME

echo "curl the endpoint as test"
curl -X GET https://api.voxana.ai/upload/voice

cd ..
