import datetime
from typing import Optional

import boto3
import json
import os
import subprocess
import time

from dataclasses import asdict, is_dataclass

from datashare import DataEntry, EmailParams, PersonDataEntry, DataEntryKey

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

    # TODO(P0, devx): Generalize to any table.
    def write_dataclass(self, data: DataEntry):
        print(f"write_dataclass {data}")
        # Convert the data_entry object to a dictionary, and then json.dumps
        # the complex objects to store them as strings in DynamoDB.
        item_dict = asdict(data)
        for key, value in item_dict.items():
            if is_dataclass(value):
                item_dict[key] = json.dumps(asdict(value))
            elif isinstance(value, dict):
                # TODO(P2, devx): Technically, we should support key -> dataclass here.
                # Just a data-class
                if key == 'email_reply_params':
                    item_dict[key] = json.dumps(value)
            elif isinstance(value, list):
                # List of Dataclasses
                if key == 'output_people_snapshot':
                    item_dict[key] = json.dumps(
                        [asdict(item) if is_dataclass(item) else item for item in value]
                    )
            elif isinstance(value, datetime.datetime):
                item_dict[key] = value.isoformat()
            else:
                print(f"skipping {key} as basic type")

        print(f"data_entry_dict: {item_dict}")
        return self.data_entry_table.put_item(Item=item_dict)

    # TODO(P1, devx): Generalize this to any data-class -
    #  - MAYBE we can include class information on the object when serializing.
    def read_into_dataclass(self, key: DataEntryKey) -> Optional[DataEntry]:
        response = self.data_entry_table.get_item(
            Key={
                'user_id': key.user_id,
                'event_name': key.event_name
            }
        )
        if 'Item' not in response:
            print(f"Item with key {key} NOT found")
            return None

        result_dict = response['Item']
        # Iterate over the items in the dictionary
        for key, value in result_dict.items():
            if isinstance(value, str):
                # If the value is a string, it might be a JSON-encoded complex object or a datetime
                try:
                    # Try to JSON decode the value
                    value = json.loads(value)
                except json.JSONDecodeError:
                    # If JSON decoding fails, it might be a datetime string
                    try:
                        value = datetime.datetime.fromisoformat(value)
                    except ValueError:
                        # If it's not a datetime string, leave it as is
                        pass

            # If the value is a dictionary or list, it might represent a dataclass
            if isinstance(value, dict):
                if key == 'email_reply_params':
                    result_dict[key] = EmailParams(**value)
            elif isinstance(value, list):
                if key == 'output_people_snapshot':
                    result_dict[key] = [PersonDataEntry(**item) if isinstance(item, dict) else item for item in value]
            elif isinstance(value, datetime.datetime):
                result_dict[key] = value

        return DataEntry(**result_dict)

    def get_table_if_exists(self, table_name):
        existing_tables = [t.name for t in self.dynamodb.tables.all()]
        print(f"existing_tables: {existing_tables}")

        if table_name in existing_tables:
            print(f"Table {table_name} already exists.")
            return self.dynamodb.Table(TABLE_NAME_DATA_ENTRY)

        return None

    def create_data_entry_table_if_not_exists(self):
        result = self.get_table_if_exists(TABLE_NAME_DATA_ENTRY)
        if result is not None:
            return result

        return self.create_table_with_option(
            table_name=TABLE_NAME_DATA_ENTRY,
            pk_name="user_id",
            sk_name="event_name",
            has_sort_key=True,
            has_gsi=False
        )

    def create_person_table_if_not_exists(self):
        result = self.get_table_if_exists(TABLE_NAME_PERSON)
        if result is not None:
            return result

        return self.create_table_with_option(
            table_name = TABLE_NAME_PERSON,
            pk_name="user_id",
            sk_name="name",
        )

    def create_user_table_if_not_exists(self):
        result = self.get_table_if_exists(TABLE_NAME_USER)
        if result is not None:
            return result

        # TODO(clean, P2): Would be nice to somehow derive the schema with compile-time checks.
        return self.create_table_with_option(
            table_name = TABLE_NAME_USER,
            pk_name="user_id",
            sk_name="email",
            has_sort_key=False,
            has_gsi=True,
        )

    # TODO(P1, utils): Currently we require primary_key (pk) and sort_key (sk) to be strings.
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
def load_files_to_dynamodb(manager: DynamoDBManager, directory: str):
    for filename in os.listdir(directory):
        with open(f"{directory}/{filename}", 'r') as file:
            data_entry = json.load(file)
            print(f"load_files_to_dynamodb importing fixture {filename} key={data_entry.user_id, data_entry.event_name}")
            manager.write_dataclass(data_entry)


def setup_dynamodb_local():
    port = 8000
    try:
        print(f"gonna kill lagging local dynamodb if running on port {port}")
        pid = subprocess.check_output(['lsof', '-i', f':{port}', '|', 'awk', '{print $2}', '|', 'tail', '-1'])
        pid = pid.decode('utf-8').strip()  # Convert bytes to string and remove extra whitespace

        # Kill the process
        subprocess.check_output(['kill', '-9', pid])
    except subprocess.CalledProcessError:
        pass

    # Startup the local DynamoDB
    cmd = 'java -Djava.library.path=' + LIB_PATH + ' -jar ' + JAR_PATH + f" -sharedDb -inMemory -port {port}"
    dynamodb_process = subprocess.Popen(cmd, shell=True)

    # Sleep for a short while to ensure DynamoDB Local has time to start up
    print("Sleeping until DynamoDB becomes available")
    time.sleep(1)

    manager = DynamoDBManager(endpoint_url='http://localhost:8000')

    return dynamodb_process, manager


def teardown_dynamodb_local(dynamodb_process):
    # Terminate the DynamoDB Local process
    dynamodb_process.terminate()


if __name__ == "__main__":
    process, mngr = setup_dynamodb_local()

    load_files_to_dynamodb(mngr, "test/fixtures/dynamodb")

    teardown_dynamodb_local(process)
