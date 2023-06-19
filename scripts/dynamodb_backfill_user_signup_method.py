import boto3


def update_items(dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    table = dynamodb.Table('KatkaAI_User')
    # Depending on the amount of data, you might need to adjust the page size
    page_size = 100
    response = table.scan(Limit=page_size)

    with table.batch_writer() as batch:
        while 'LastEvaluatedKey' in response:
            for item in response['Items']:
                item['signup_method'] = 'email'
                batch.put_item(Item=item)

            # Fetch the next page
            if 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'], Limit=page_size)

        # Final batch for items
        for item in response['Items']:
            item['signup_method'] = 'email'
            batch.put_item(Item=item)


if __name__ == '__main__':
    update_items()