import boto3
import os
import json
import datetime

s3 = boto3.client("s3")
BUCKET = os.environ["UPLOAD_BUCKET"]

def handler(event, context):
    # Parse request (e.g. get user id, platform, data_type, filename)
    body = json.loads(event['body'])
    user_id = body['user_id']
    platform = body.get('platform', 'tiktok')
    data_type = body.get('data_type', 'videos')
    filename = body.get('filename', 'data.json')
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    s3_key = f"uploads/platform={platform}/date={today}/type={data_type}/user={user_id}/{filename}"

    presigned_url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': BUCKET, 'Key': s3_key, 'ContentType': 'application/json'},
        ExpiresIn=900
    )
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'url': presigned_url, 'key': s3_key})
    }
