# TODO(P0, devx): Figure out how to deploy this easily.
from typing import Optional

import boto3
import json
import re

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

print('Loading function')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('KatkaAI_User')


def respond(err: Optional[Exception], res=None):
    return {
        'statusCode': '400' if err else '200',
        'body': str(err) if err else json.dumps(res),
        'headers': {
            'Content-Type': 'application/json',
        },
    }


def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))

    operations = {
        'PUT': lambda x: update_item(x),
    }

    operation = event['httpMethod']
    if operation in operations:
        payload = json.loads(event['body'])
        return respond(None, operations[operation](payload))
    else:
        return respond(ValueError('Unsupported method "{}"'.format(operation)))


def extract_email(message):
    pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    match = re.search(pattern, message)
    return match.group(0) if match else None


def update_item(payload):
    phone_number = payload['phone_number']
    message = payload['message']
    new_email = extract_email(message)
    # TODO(handle subscribe/unsubscribe)
    if new_email is None:
        raise ValueError(f"No valid email found in message: {message}")

    # Query GSI to get primary key
    response = table.query(
        IndexName='KatkaAI_User_phone_number_index',
        KeyConditionExpression=Key('phone_number').eq(phone_number)
    )

    items = response['Items']
    if not items:
        raise Exception('No item found with the given phone_number')

    primary_key = items[0]['user_id']
    full_name = items[0].get('full_name', "")

    # Update email
    response = table.update_item(
        Key={
            'user_id': primary_key
        },
        UpdateExpression='SET email_address = :val1',
        ExpressionAttributeValues={
            ':val1': new_email
        }
    )

    send_email(user_id=primary_key, email=new_email, full_name=full_name)

    return response


def get_data(user_id):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('KatkaAI_DataEntry')

    try:
        response = table.query(
            KeyConditionExpression=Key('user_id').eq(user_id)
        )
    except ClientError as e:
        print(f"Unable to query table: {e}")
        return None

    return response['Items']


def build_email_body(user_id, full_name):
    items = get_data(user_id)

    if items is None:
        return 'Error occured, please contact support: petherz@gmail.com, kata.sabo@gmail.com'

    line_items = []
    for item in items:
        event_name = item.get('event_name', "event_name")
        output_webpage_url = item.get('output_webpage_url', None)
        if output_webpage_url is None:
            print(f"Skipping item {event_name} as output_webpage_url is None")
            continue
        line_items.append(f"{event_name}: {output_webpage_url}")

    email_body = f"Hi {full_name},\n\nThe results of your event(s):\n" + '\n'.join(line_items)
    email_body += '\nThank you!\nYour team at Katka.ai\n'
    email_body += 'Contact support: petherz@gmail.com, kata.sabo@gmail.com'

    return email_body


def send_email(user_id, email, full_name):
    ses = boto3.client('ses')

    try:
        return ses.send_email(
            Source="Katka.AI <assistant@katka.ai>",  # SES verified email
            Destination={
                'ToAddresses': [
                    email,
                ],
                'BccAddresses': ["petherz@gmail.com", "kata.sabo@gmail.com"]
            },
            Message={
                'Subject': {
                    'Data': 'Your event information',
                },
                'Body': {
                    'Text': {
                        'Data': build_email_body(user_id, full_name)
                    },
                },
            }
        )
    except ClientError as e:
        print(f"Failed to send email: {e}")
