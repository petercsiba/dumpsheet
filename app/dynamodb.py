import boto3
import json
import os
import subprocess
import time

from botocore.exceptions import ClientError
from dataclasses import dataclass
from typing import Optional, Type, Any

from datashare import DataEntry, dataclass_to_json, User, dict_to_dataclass

# TODO(P2, security): Ideally the Lambda should only have permissions to these tables
# https://us-east-1.console.aws.amazon.com/iam/home#/roles/katka-ai-container-lambda-role-iadxzlko$createPolicy?step=edit
TABLE_NAME_DATA_ENTRY = "KatkaAI_DataEntry"
TABLE_NAME_EMAIL_LOG = "KatkaAI_EmailLog"  # To prevent double-sending
TABLE_NAME_PERSON = "KatkaAI_Person"
TABLE_NAME_PROMPT = "KatkaAI_PromptLog"
TABLE_NAME_USER = "KatkaAI_User"

# For local runs
JAR_PATH = 'DynamoDBLocal.jar'
LIB_PATH = './DynamoDBLocal_lib'
TEST_TRANSCRIPT_PATH = "test/fixtures/transcripts/"


def write_data_class(table, data: dataclass, require_success=True):
    print(f"write_data_entry {type(data)}")
    # TODO(p2, quite very hacky)
    item_json = dataclass_to_json(data)
    item_dict = json.loads(item_json)

    try:
        return table.put_item(Item=item_dict)
    except TypeError as err:
        print(f"ERROR: Could NOT serialize to {table.table_name} item {item_dict}")
        if require_success:
            raise err
        else:
            return None


def read_data_class(data_class_type: Type[Any], table, key, print_not_found=True):
    try:
        response = table.get_item(Key=key)
    except ClientError as err:
        table_describe = table.meta.client.describe_table(TableName=table.table_name)
        print(f"ERROR: read_data_class ClientError for key {key} cause for table {table_describe}: {err}")
        raise err

    if 'Item' not in response:
        if print_not_found:
            print(f"Item with key {key} NOT found in {table}")
        return None

    item_dict = response['Item']
    return dict_to_dataclass(dict_=item_dict, data_class_type=data_class_type)


class DynamoDBManager:
    def __init__(self, endpoint_url):
        self.dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
        self.user_table = self.create_user_table_if_not_exists()
        self.data_entry_table = self.create_data_entry_table_if_not_exists()
        self.email_log_table = self.create_email_log_table_if_not_exists()
        self.person_table = self.create_person_table_if_not_exists()
        self.prompt_table = self.create_prompt_table_if_not_exists()

    def write_data_entry(self, data_entry: DataEntry):
        return write_data_class(self.data_entry_table, data_entry)

    def read_data_entry(self, user_id, event_name) -> Optional[DataEntry]:
        return read_data_class(DataEntry, self.data_entry_table, {
                'user_id': user_id,
                'event_name': event_name
            }
        )
    # TODO(P2, devx): dynamodb.update is safer but no-time.

    def write_user(self, user: User):
        return write_data_class(self.user_table, user)

    def read_user(self, user_id) -> Optional[User]:
        return read_data_class(User, self.user_table, {
                'user_id': user_id,
            }
                               )

    def get_table_if_exists(self, table_name):
        existing_tables = [t.name for t in self.dynamodb.tables.all()]
        print(f"existing_tables: {existing_tables}")

        if table_name in existing_tables:
            print(f"Table {table_name} already exists.")
            return self.dynamodb.Table(table_name)

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

    def create_email_log_table_if_not_exists(self):
        result = self.get_table_if_exists(TABLE_NAME_EMAIL_LOG)
        if result is not None:
            return result

        return self.create_table_with_option(
            table_name=TABLE_NAME_EMAIL_LOG,
            pk_name="email_to",
            sk_name="idempotency_key",
        )

    def create_person_table_if_not_exists(self):
        result = self.get_table_if_exists(TABLE_NAME_PERSON)
        if result is not None:
            return result

        return self.create_table_with_option(
            table_name=TABLE_NAME_PERSON,
            pk_name="user_id",
            sk_name="name",
        )

    def create_prompt_table_if_not_exists(self):
        result = self.get_table_if_exists(TABLE_NAME_PROMPT)
        if result is not None:
            return result

        return self.create_table_with_option(
            table_name=TABLE_NAME_PROMPT,
            pk_name="prompt_hash",
            sk_name="model",
        )

    def create_user_table_if_not_exists(self):
        result = self.get_table_if_exists(TABLE_NAME_USER)
        if result is not None:
            return result

        # TODO(clean, P2): Would be nice to somehow derive the schema with compile-time checks.
        return self.create_table_with_option(
            table_name=TABLE_NAME_USER,
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
        key_schema = [
            {
                'AttributeName': pk_name,
                'KeyType': 'HASH'  # Partition key
            },
        ]
        attribute_definitions = [
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
            key_schema.append({
                'AttributeName': sk_name,
                'KeyType': 'RANGE'  # Sort key
            })

        table_args = {
            'TableName': table_name,
            'KeySchema': key_schema,
            'AttributeDefinitions': attribute_definitions,
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
        print(f"Waiting for dynamodb table to be created {table_name}")
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)

        print(f"Table {table_name} status:", table.table_status)
        return table


# ========== MOSTLY LOCAL SHIT =========== #
def load_files_to_dynamodb(manager: DynamoDBManager, directory: str):
    for filename in os.listdir(directory):
        with open(f"{directory}/{filename}", 'r') as file:
            data_entry = json.load(file)
            print(f"load_files_to_dynamodb importing {filename} key={data_entry.user_id, data_entry.event_name}")
            manager.write_data_entry(data_entry)


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
    # NOTE: add -inMemory if you want to truncate it after each run.
    cmd = 'java -Djava.library.path=' + LIB_PATH + ' -jar ' + JAR_PATH + f" -sharedDb -port {port}"
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
