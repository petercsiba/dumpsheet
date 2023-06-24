#!/bin/bash

KATKA_AI_API_KEY="<ACTUAL_KEY>"
URL="https://k4qviavjh1.execute-api.us-west-2.amazonaws.com/prod/user"  # replace with your actual API Gateway URL
PHONE_NUMBER="+16502106516"  # replace with a test phone number
MESSAGE="test2@example.com"  # replace with a test message

curl -X PUT \
  -H "x-api-key: ${KATKA_AI_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"phone_number":"'${PHONE_NUMBER}'", "message":"'${MESSAGE}'"}' \
  ${URL}