## Local Setup
Setup Python your preferred way (virtualenv recommended)

### Run tests
For now, most of the Python files have a `if __name__ == "__main__":` which essentially runs a test.
So you can test the lambda logic by:
```bash
# inside the neomi/ directory
pyenv activate neomi  # just making sure
python -m app.app
```
TLDR; The `neomi` project is now installed as a module through `setup.py`, so we can conclude research like:
```bash
python -m research.action_based_transition
```

### Setup DynamoDB Local (GPT generated)
* Requires JAVA, verify with `java -version`
* Download (DynamoDB Tar)[https://s3.us-west-2.amazonaws.com/dynamodb-local/dynamodb_local_latest.tar.gz]
* OR just `curl -O https://dynamodb-local.s3.us-west-2.amazonaws.com/dynamodb_local_latest.tar.gz
`
* Unpack `tar -xvf dynamodb_local_latest.tar`
* `app/app.py` starts it itself, if you need it you can start it with (default port is 8000): `java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb`

### Setup Other Requirements
* ffmpeg: 

### Running the Lambda locally
This is tricky for our case as it's triggered by an email stored in S3,
so prefer `python -m app.app`.
```
docker build -t hello-world .
docker run -p 9000:8080 hello-world
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
```

## Deployment
The lambda image lives in https://us-west-2.console.aws.amazon.com/ecr/repositories?region=us-west-2

### Set up AWS config
```
# ~/.aws/config
[default]
region=us-west-2

# ~/.aws/credentials
[default]
aws_access_key_id=
aws_secret_access_key=
```

### Push New Image
Yeah hardcoded stuff - but it works!
```
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 680516425449.dkr.ecr.us-west-2.amazonaws.com
docker build -t 680516425449.dkr.ecr.us-west-2.amazonaws.com/networking-summary-lambda:latest .
docker push 680516425449.dkr.ecr.us-west-2.amazonaws.com/networking-summary-lambda:latest
```

### Deploy Lambda
A few manual clicks in AWS console:
* Go to Lambda
* Click on deploy new image
* Click through to find the newest
* You can re-run it by re-uploading to S3 some of the previous files. 

# Oncall
# * Usage https://platform.openai.com/account/usage