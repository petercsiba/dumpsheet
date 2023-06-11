import boto3
import json
import pandas as pd
import subprocess
import time

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from dataclasses import dataclass
from typing import Optional, Type, Any, List

from datashare import DataEntry, dataclass_to_json, User, dict_to_dataclass


# TODO(P2, security): Ideally the Lambda should only have permissions to these tables
# https://us-east-1.console.aws.amazon.com/iam/home#/roles/katka-ai-container-lambda-role-iadxzlko$createPolicy?step=edit
TABLE_NAME_DATA_ENTRY = "KatkaAI_DataEntry"
TABLE_NAME_EMAIL_LOG = "KatkaAI_EmailLog"  # To prevent double-sending
TABLE_NAME_PROMPT = "KatkaAI_PromptLog"
TABLE_NAME_USER = "KatkaAI_User"

# For local runs
JAR_PATH = 'DynamoDBLocal.jar'
LIB_PATH = './DynamoDBLocal_lib'
TEST_TRANSCRIPT_PATH = "test/fixtures/transcripts/"


def generate_index_name(table_name, attr_name):
    return f"{table_name}_{attr_name}_index"


def write_data_class(table, data: dataclass, require_success=True):
    # TODO(P2, devx): This is quite hacky way to translate datetime and other field to what DynamoDB likes
    item_json = dataclass_to_json(data)
    item_dict = json.loads(item_json)

    try:
        return table.put_item(Item=item_dict)
    except TypeError as err:
        print(f"ERROR: DynamoDB could NOT serialize to {table.table_name} item {item_dict}")
        if require_success:
            raise err
        else:
            return None

# TODO(P1, devx): Support updates, sth like, unsure how with dataclass
# response = table.update_item(
#     Key={
#         'your-partition-key-name': 'partition-key-value',
#         'your-sort-key-name': 'sort-key-value'
#     },
#     UpdateExpression='SET your-attribute-name = :val1',
#     ExpressionAttributeValues={
#         ':val1': 'new-value'
#     },
#     ReturnValues="UPDATED_NEW"
# )


def read_data_class(data_class_type: Type[Any], table, key, print_not_found=True):
    try:
        response = table.get_item(Key=key)
    except ClientError as err:
        table_describe = table.meta.client.describe_table(TableName=table.table_name)
        print(f"ERROR: DynamoDB read_data_class ClientError for key {key} cause for table {table_describe}: {err}")
        raise err

    if 'Item' not in response:
        if print_not_found:
            print(f"DynamoDB: Item with key {key} NOT found in {table}")
        return None

    item_dict = response['Item']
    return dict_to_dataclass(dict_=item_dict, dataclass_type=data_class_type)


def read_all_data_class(data_class_type: Type[Any], table, partition_key_name: str, partition_key_value: str):
    response = table.query(
        KeyConditionExpression=Key(partition_key_name).eq(partition_key_value)
    )

    if 'Items' not in response or not response['Items']:
        print(f"ERROR: DynamoDB items NOT found in {table} for partition key {partition_key_value}")
        return None

    items = response['Items']
    data_class_list = [dict_to_dataclass(dict_=item_dict, dataclass_type=data_class_type) for item_dict in items]
    print(
        f"DynamoDB: Found {len(data_class_list)} items in {table.table_name} "
        f"for {partition_key_name}={partition_key_value}"
    )
    return data_class_list


def parse_dynamodb_json(dynamodb_json):
    print(f"parse_dynamodb_json {dynamodb_json}")
    # For dictionaries, recurse on each value
    if isinstance(dynamodb_json, dict):
        if len(dynamodb_json) == 1:
            # If there's only one item, check for DynamoDB type descriptors and handle them
            type_descriptor, value = next(iter(dynamodb_json.items()))
            if type_descriptor == 'S':
                return value
            elif type_descriptor == 'NULL':
                return None
            elif type_descriptor == 'L':
                return [parse_dynamodb_json(item) for item in value]
            elif type_descriptor == 'N':
                return float(value)
            elif type_descriptor == 'M':
                return {key: parse_dynamodb_json(val) for key, val in value.items()}
        else:
            # If there are multiple items, just recurse on each one
            return {key: parse_dynamodb_json(value) for key, value in dynamodb_json.items()}
    elif isinstance(dynamodb_json, list):
        # For list, just recurse on each item
        return [parse_dynamodb_json(item) for item in dynamodb_json]
    else:
        # For anything else (e.g., a string, int, float), just return the value
        return dynamodb_json


def load_csv_to_dataclass(data_class_type: Type[Any], csv_filepath: str) -> List[Any]:
    # Load the CSV file to a DataFrame
    loaded_df = pd.read_csv(csv_filepath)
    print(f"Loading {csv_filepath} found columns {loaded_df.columns}")

    # Initialize an empty list to store the dataclass instances
    data_entries = []

    # Iterate over each row in the DataFrame
    for _, row in loaded_df.iterrows():
        row_dict = row.to_dict()
        print(f"row_dict {row_dict}")
        # Convert any JSON strings in the row to Python objects
        for key, value in row_dict.items():
            if isinstance(value, str):
                try:
                    # Try to load JSON
                    loaded_json = json.loads(value)
                    # If loading succeeds, then parse the DynamoDB JSON format
                    row_dict[key] = parse_dynamodb_json(loaded_json)
                except json.JSONDecodeError:
                    pass  # Not a JSON string, leave as is

        data_entry = dict_to_dataclass(row_dict, data_class_type)
        data_entries.append(data_entry)

    # Return the list of dataclass instances
    print(f"Parsed {len(data_entries)} items of {data_class_type} from {csv_filepath}")
    return data_entries


class DynamoDBManager:
    def __init__(self, endpoint_url):
        self.dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
        self.user_table = self.create_user_table_if_not_exists()
        self.data_entry_table = self.create_data_entry_table_if_not_exists()
        self.email_log_table = self.create_email_log_table_if_not_exists()
        self.prompt_table = self.create_prompt_table_if_not_exists()

    def write_data_entry(self, data_entry: DataEntry):
        return write_data_class(self.data_entry_table, data_entry)

    def read_data_entry(self, user_id, event_name) -> Optional[DataEntry]:
        return read_data_class(DataEntry, self.data_entry_table, {
                'user_id': user_id,
                'event_name': event_name
            }
        )

    def get_all_data_entries_for_user(self, user_id) -> List[DataEntry]:
        return read_all_data_class(
            DataEntry,
            self.data_entry_table,
            partition_key_name='user_id',
            partition_key_value=user_id
        )

    # TODO(P2, devx): dynamodb.update is safer but no-time.

    def get_or_create_user(self, email_address: str) -> User:
        # NOTE: Cannot user read_data_class as that requires user_id
        response = self.user_table.query(
            IndexName=generate_index_name(self.user_table.table_name, "email_address"),
            KeyConditionExpression='email_address = :email',
            ExpressionAttributeValues={
                ':email': email_address
            }
        )
        items = response['Items']
        if items is None or len(items) == 0:
            new_user = User(
                user_id=User.generate_user_id(email_address=email_address),
                email_address=email_address,
            )
            print(f"DynamoDB: creating new user {new_user.user_id} for {new_user.email_address}!")
            write_data_class(self.user_table, data=new_user)
            return new_user

        if len(items) > 1:
            print(f"WARNING: DynamoDB found multiple users for email_address {email_address}, returning first")

        result: User = dict_to_dataclass(items[0], dataclass_type=User)
        print(f"DynamoDB: found existing user {result.user_id} for {result.email_address}")
        return result

    def get_table_if_exists(self, table_name):
        existing_tables = [t.name for t in self.dynamodb.tables.all()]
        print(f"DynamoDB: existing_tables: {existing_tables}")

        if table_name in existing_tables:
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
            sk_name="email_address",
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
            index_name = generate_index_name(table_name=table_name, attr_name=sk_name)
            print(f"DynamoDB: creating GlobalSecondaryIndexes for {index_name}")
            table_args['GlobalSecondaryIndexes'] = [
                {
                    'IndexName': index_name,
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
        print(f"DynamoDB: waiting for table to be created {table_name}")
        table.meta.client.get_waiter('table_exists').wait(TableName=table_name)

        print(f"DynamoDB: table {table_name} status:", table.table_status)
        return table


# ========== MOSTLY LOCAL SHIT =========== #
def setup_dynamodb_local():
    port = 8000
    try:
        print(f"DynamoDB: gonna kill lagging local if running on port {port}")
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
    print("DynamoDB: Sleeping until DynamoDB becomes available")
    time.sleep(1)

    manager = DynamoDBManager(endpoint_url='http://localhost:8000')

    return dynamodb_process, manager


def teardown_dynamodb_local(dynamodb_process):
    # Terminate the DynamoDB Local process
    dynamodb_process.terminate()


if __name__ == "__main__":
    process, mngr = setup_dynamodb_local()

    teardown_dynamodb_local(process)
