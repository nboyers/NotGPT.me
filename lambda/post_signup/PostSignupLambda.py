from xml.dom.minidom import Attr
import boto3
import os
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['USER_TABLE_NAME'])


def handler(event, context):
    user_id = event['request']['userAttributes']['sub']
    email = event['request']['userAttributes'].get('email', '')

    item = {
        "userId": user_id,
        "email": email,
        "plan": "free",
        "credits": 5,
        "used": 0,
        "platformsUsed": [],
        "createdAt": int(time.time()),
        "lastActiveAt": int(time.time()),
        "agreedToTerms": True,
    }

    table.put_item(
        Item=item,
        ConditionExpression=Attr('userId').not_exists()
    )
    return event  # Required to continue the Cognito signup flow
