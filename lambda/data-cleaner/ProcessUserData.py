import boto3 # type: ignore
import os
import json
import datetime
from urllib.parse import unquote_plus

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
BUCKET = os.environ["UPLOAD_BUCKET"]
AGGREGATION_TABLE = os.environ["AGGREGATION_TABLE"]

def handler(event, context):
    """Process S3 upload events and update aggregation tables"""
    
    # Process S3 event
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        
        # Determine if this is a private or collective upload
        if key.startswith('private/'):
            process_private_upload(bucket, key)
        elif key.startswith('collective/'):
            process_collective_upload(bucket, key)
        else:
            # Legacy path format
            process_legacy_upload(bucket, key)

def process_private_upload(bucket, key):
    """Process a private user upload"""
    try:
        # Extract user_id from the key
        # Format: private/user={user_id}/platform={platform}/date={date}/{filename}
        parts = key.split('/')
        user_id = parts[1].split('=')[1]
        platform = parts[2].split('=')[1]
        
        # Get the file content
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        data = json.loads(content)
        
        # Process the data and update user-specific stats
        # This would be expanded based on the actual data structure
        table = dynamodb.Table(AGGREGATION_TABLE)
        
        # Update user-specific stats
        table.put_item(
            Item={
                'stat_type': f'user_{user_id}_{platform}',
                'period': datetime.datetime.now().strftime("%Y-%m-%d"),
                'data_count': len(data) if isinstance(data, list) else 1,
                'last_updated': datetime.datetime.now().isoformat()
            }
        )
        
        print(f"Processed private upload for user {user_id}")
        
    except Exception as e:
        print(f"Error processing private upload: {str(e)}")
        raise

def process_collective_upload(bucket, key):
    """Process a collective upload for anonymous users"""
    try:
        # Extract platform from the key
        # Format: collective/platform={platform}/date={date}/{filename}
        parts = key.split('/')
        platform = parts[1].split('=')[1]
        
        # Get the file content
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        data = json.loads(content)
        
        # Process the data and update collective stats
        table = dynamodb.Table(AGGREGATION_TABLE)
        
        # Update collective stats
        table.update_item(
            Key={
                'stat_type': f'collective_{platform}',
                'period': datetime.datetime.now().strftime("%Y-%m-%d")
            },
            UpdateExpression="ADD upload_count :inc SET last_updated = :now",
            ExpressionAttributeValues={
                ':inc': 1,
                ':now': datetime.datetime.now().isoformat()
            }
        )
        
        print(f"Processed collective upload for platform {platform}")
        
    except Exception as e:
        print(f"Error processing collective upload: {str(e)}")
        raise

def process_legacy_upload(bucket, key):
    """Process uploads using the old path format"""
    try:
        print(f"Processing legacy upload: {key}")
        # Extract information from the key
        # Format: uploads/platform={platform}/date={date}/type={type}/user={user_id}/{filename}
        parts = key.split('/')
        platform = parts[1].split('=')[1]
        data_type = parts[3].split('=')[1]
        user_id = parts[4].split('=')[1]
        
        # Process based on whether it's an anonymous user or not
        if user_id == 'anonymous':
            # Treat as collective
            process_collective_upload(bucket, key)
        else:
            # Treat as private
            process_private_upload(bucket, key)
            
    except Exception as e:
        print(f"Error processing legacy upload: {str(e)}")
        raise