import boto3
import os
import subprocess
import time

from dataclasses import dataclass

TRANSCRIPT_TABLE_NAME = "KatkaAI_Transcripts"

# For local runs
JAR_PATH = 'DynamoDBLocal.jar'
LIB_PATH = './DynamoDBLocal_lib'
TEST_TRANSCRIPT_PATH = "test/fixtures/transcripts/"


@dataclass
class TranscriptKey:
    email: str
    timestamp: str


class DynamoDBManager:
    def __init__(self, endpoint_url):
        self.dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
        self.transcript_table = self.dynamodb.Table(TRANSCRIPT_TABLE_NAME)

    def write_transcript(self, key: TranscriptKey, transcript: str):
        print(f"write_transcript {key} of size {len(transcript)}")
        response = self.transcript_table.put_item(
            Item={
                'email': key.email,
                'timestamp': key.timestamp,
                'transcript': transcript,
            }
        )
        return response

    def read_transcript(self, key: TranscriptKey):
        response = self.transcript_table.get_item(
            Key={
                'email': key.email,
                'timestamp': key.timestamp
            }
        )
        transcript = response['Item'] if 'Item' in response else None
        print(f"read_transcript {key} of size {'NOT FOUND' if transcript is None else len(transcript)}")

    def update_transcript(self, key: TranscriptKey, summaries, drafts):
        print(f"update_transcript {key} with summaries {len(summaries)} and drafts {len(drafts)}")
        response = self.transcript_table.update_item(
            Key={
                'email': key.email,
                'timestamp': key.timestamp
            },
            UpdateExpression="set summaries=:s, drafts=:d",
            ExpressionAttributeValues={
                ':s': summaries,
                ':d': drafts
            },
            ReturnValues="UPDATED_NEW"
        )
        return response

    def create_transcript_table_if_not_exists(self):
        existing_tables = self.transcript_table.list_tables()['TableNames']

        if TRANSCRIPT_TABLE_NAME not in existing_tables:
            self.transcript_table = self.dynamodb.create_table(
                TableName=TRANSCRIPT_TABLE_NAME,
                KeySchema=[
                    {
                        'AttributeName': 'email',
                        'KeyType': 'HASH'  # Partition key
                    },
                    {
                        'AttributeName': 'timestamp',
                        'KeyType': 'RANGE'  # Sort key
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'email',
                        'AttributeType': 'S'
                    },
                    {
                        'AttributeName': 'timestamp',
                        'AttributeType': 'S'
                    },

                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            print(f"Table {TRANSCRIPT_TABLE_NAME} creation pending, waiting ...")

            # Wait until the table exists, this will take a minute or so
            self.dynamodb.get_waiter('table_exists').wait(TableName=TRANSCRIPT_TABLE_NAME)
            print(f"Table {TRANSCRIPT_TABLE_NAME} created!")
        else:
            print(f"Table {TRANSCRIPT_TABLE_NAME} already exists.")
            self.transcript_table = self.dynamodb.Table(TRANSCRIPT_TABLE_NAME)


# ========== MOSTLY LOCAL SHIT =========== #
def write_files_to_dynamodb(manager: DynamoDBManager, directory: str):
    for filename in os.listdir(directory):
        email, timestamp = filename.rsplit('.', 1)[0].split('_')
        key = TranscriptKey(email=email, timestamp=timestamp)

        with open(f"{directory}/{filename}", 'r') as file:
            transcript = file.read()

        manager.write_transcript(key, transcript)


def setup_dynamodb_local():
    # Adjust the path to DynamoDBLocal.jar and DynamoDBLocal_lib as needed
    cmd = 'java -Djava.library.path=' + LIB_PATH + ' -jar ' + JAR_PATH + ' -sharedDb -inMemory'
    dynamodb_process = subprocess.Popen(cmd, shell=True)

    # Sleep for a short while to ensure DynamoDB Local has time to start up
    print("Sleeping until DynamoDB becomes available")
    time.sleep(1)

    manager = DynamoDBManager(endpoint_url='http://localhost:8000')
    manager.create_transcript_table_if_not_exists()
    write_files_to_dynamodb()

    return dynamodb_process, manager


def teardown_dynamodb_local(dynamodb_process):
    # Terminate the DynamoDB Local process
    dynamodb_process.terminate()


if __name__ == "__main__":
    process = setup_dynamodb_local()

    write_files_to_dynamodb('test/fixtures/transcripts')

    teardown_dynamodb_local(process)
