#!/bin/bash

PROFILE_NAME="PowerUserAccess-831154875375"

# Check if logged into AWS CLI by trying to list S3 buckets
aws s3 ls --profile $PROFILE_NAME > /dev/null 2>&1

# If previous command failed, assume not logged in and login to SSO
if [ $? -ne 0 ]; then
    aws sso login --profile $PROFILE_NAME
fi

# Get ECR login password and login to Docker
aws ecr get-login-password --region us-east-1 --profile $PROFILE_NAME | docker login --username AWS --password-stdin 831154875375.dkr.ecr.us-east-1.amazonaws.com

# For some weird reason the first build try always fails :/ So always retry once on failure
docker build -t 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups . || docker build -t 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups .

docker push 831154875375.dkr.ecr.us-east-1.amazonaws.com/draft-your-follow-ups:latest

# echo "To finish deploy, log-in to AWS: https://d-90679cf568.awsapps.com/start/"

echo "Go to lambda and select latest container https://us-east-1.console.aws.amazon.com/lambda/home?region=us-east-1#/functions/draft-your-follow-ups/edit/image-settings?tab=code"