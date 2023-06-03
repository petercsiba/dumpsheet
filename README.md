## Local Setup
Setup Python your preferred way (virtualenv recommended)

Setup DynamoDB Local (GPT generated)
* Requires JAVA, verify with `java -version`
* Download (DynamoDB Tar)[https://s3.us-west-2.amazonaws.com/dynamodb-local/dynamodb_local_latest.tar.gz]
* Unpack `tar -xvf dynamodb_local_latest.tar`
* Start it (default port is 8000): `java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb`