#!/bin/sh
echo "Running entry.sh"
echo "AWS_LAMBDA_RUNTIME_API: ${AWS_LAMBDA_RUNTIME_API}"
if [ -z "${AWS_LAMBDA_RUNTIME_API}" ]; then
    echo "Running /usr/bin/aws-lambda-rie"
    exec /usr/bin/aws-lambda-rie /usr/local/bin/python -m awslambdaric $1
else
    echo "Running /usr/local/bin/python"
    exec /usr/local/bin/python -m awslambdaric $1
fi