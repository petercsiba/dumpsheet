import boto3
import json
import os
import subprocess
import time

from dataclasses import dataclass, asdict

from datashare import DataEntry, EmailParams, Person, DataEntryKey

TABLE_NAME_DATA_ENTRY = "KatkaAI_DataEntry"
TABLE_NAME_PERSON = "KatkaAI_Person"
TABLE_NAME_USER = "KatkaAI_User"

# For local runs
JAR_PATH = 'DynamoDBLocal.jar'
LIB_PATH = './DynamoDBLocal_lib'
TEST_TRANSCRIPT_PATH = "test/fixtures/transcripts/"


class DynamoDBManager:
    def __init__(self, endpoint_url):
        self.dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
        self.user_table = self.create_user_table_if_not_exists()
        self.data_entry_table = self.create_data_entry_table_if_not_exists()
        self.person_table = self.create_person_table_if_not_exists()

    def write_data_entry(self, data_entry: DataEntry):
        print(f"write_data_entry for user_id {data_entry.user_id} event_name {data_entry.event_name}")
        # Convert the data_entry object to a dictionary, and then json.dumps
        # the complex objects to store them as strings in DynamoDB.
        data_entry_dict = asdict(data_entry)
        for key, value in data_entry_dict.items():
            if isinstance(value, (EmailParams, Person, dict)):
                data_entry_dict[key] = json.dumps(asdict(value))
            elif isinstance(value, list):
                data_entry_dict[key] = json.dumps(
                    [asdict(item) if isinstance(item, (EmailParams, Person)) else item for item in value]
                )

        return self.data_entry_table.put_item(Item=data_entry_dict)

    def read_data_entry(self, key: DataEntryKey) -> DataEntry:
        response = self.data_entry_table.get_item(
            Key={
                'user_id': key.user_id,
                'event_name': key.event_name
            }
        )
        transcript = response['Item'] if 'Item' in response else None
        print(f"read_transcript {key} of size {'NOT FOUND' if transcript is None else len(transcript)}")

    def update_transcript(self, key: DataEntryKey, summaries, drafts):
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

    def create_data_entry_table_if_not_exists(self):
        existing_tables = self.dynamodb.list_tables()['TableNames']

        if TABLE_NAME_DATA_ENTRY in existing_tables:
            print(f"Table {TABLE_NAME_DATA_ENTRY} already exists.")
            return self.dynamodb.Table(TABLE_NAME_DATA_ENTRY)

        return self.create_table_with_option(
            table_name = TABLE_NAME_DATA_ENTRY,
            pk_name="user_id",
            sk_name="email",
            has_sort_key=True,
            has_gsi=False
        )

    def create_person_table_if_not_exists(self):
        existing_tables = self.dynamodb.list_tables()['TableNames']

        if TABLE_NAME_PERSON in existing_tables:
            print(f"Table {TABLE_NAME_PERSON} already exists.")
            return self.dynamodb.Table(TABLE_NAME_PERSON)

        return self.create_table_with_option(
            table_name = TABLE_NAME_PERSON,
            pk_name="user_id",
            sk_name="name",
        )

    def create_user_table_if_not_exists(self):
        existing_tables = self.dynamodb.list_tables()['TableNames']

        if TABLE_NAME_USER in existing_tables:
            print(f"Table {TABLE_NAME_USER} already exists.")
            return self.dynamodb.Table(TABLE_NAME_USER)

        # TODO(clean, P2): Would be nice to somehow derive the schema with compile-time checks.
        return self.create_table_with_option(
            table_name = TABLE_NAME_USER,
            pk_name="user_id",
            sk_name="email",
            has_sort_key=False,
            has_gsi=True,
        )

    # TODO(P1, utils): Currentluy we require primary_key (pk) and sort_key (sk) to be strings.
    def create_table_with_option(
            self,
            table_name: str,
            pk_name: str,
            sk_name: str,
            has_sort_key: bool = True,
            has_gsi: bool = False
    ):
        KeySchema = [
            {
                'AttributeName': pk_name,
                'KeyType': 'HASH'  # Partition key
            },
        ]
        AttributeDefinitions = [
            {
                'AttributeName': pk_name,
                'AttributeType': 'S'  # 'S' stands for String
            },
            {
                'AttributeName': sk_name,
                'AttributeType': 'S'
            },
        ]

        if has_sort_key:
            KeySchema.append({
                'AttributeName': sk_name,
                'KeyType': 'RANGE'  # Sort key
            })

        table_args = {
            'TableName': table_name,
            'KeySchema': KeySchema,
            'AttributeDefinitions': AttributeDefinitions,
            'ProvisionedThroughput': {
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            },
        }

        if has_gsi:
            table_args['GlobalSecondaryIndexes'] = [
                {
                    'IndexName': f'{sk_name}_index',
                    'KeySchema': [
                        {
                            'AttributeName': sk_name,
                            'KeyType': 'HASH'  # Partition key
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    },
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ]

        table = self.dynamodb.create_table(**table_args)
        # Wait until the table exists.
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)

        print(f"Table {table_name} status:", table.table_status)


# ========== MOSTLY LOCAL SHIT =========== #
def write_files_to_dynamodb(manager: DynamoDBManager, directory: str):
    for filename in os.listdir(directory):
        email, timestamp = filename.rsplit('.', 1)[0].split('_')
        key = DataEntryKey(email=email, timestamp=timestamp)

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
