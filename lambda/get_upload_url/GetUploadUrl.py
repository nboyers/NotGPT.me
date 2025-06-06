import boto3 
from boto3.dynamodb.conditions import Attr
import os
import json
import datetime

s3 = boto3.client("s3")
BUCKET = os.environ["UPLOAD_BUCKET"]

def handler(event, context):
    body = json.loads(event.get('body', '{}'))
    user_id = body.get('user_id', 'anonymous')
    platform = body.get('platform', 'tiktok')
    data_type = body.get('data_type', 'data')
    filename = body.get('filename', 'data.json')
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    key = f"uploads/platform={platform}/date={today}/type={data_type}/user={user_id}/{filename}"
    url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': BUCKET, 'Key': key, 'ContentType': 'application/json'},
        ExpiresIn=900
    )
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({'url': url, 'key': key})
    }
