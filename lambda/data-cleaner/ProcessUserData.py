from boto3 import client, resource # type: ignore
from os import environ
from json import loads, dumps
from hashlib import sha256
from re import compile as re_compile
from datetime import datetime
from urllib.parse import unquote_plus
from boto3.dynamodb.conditions import Key

s3 = client("s3")
glue = client("glue")
dynamodb = resource('dynamodb')
table = dynamodb.Table(environ['AGGREGATION_TABLE'])
BUCKET = environ["UPLOAD_BUCKET"]
CRAWLER_NAME = environ["CRAWLER_NAME"]
HASHTAG_RE = re_compile(r"#(\w{2,50})")

def normalize_upload_for_glue(bucket, key):
    """Normalize uploaded data into structured format for Glue Catalog"""
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8", errors="ignore")
        data = loads(content) if content.strip() else {}
        
        upload_id = sha256(f"{key}_{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        timestamp = datetime.now().isoformat()
        
        # Extract videos
        videos = extract_videos(data)
        for i, video in enumerate(videos):
            video_record = {
                "upload_id": upload_id,
                "video_id": f"{upload_id}_{i}",
                "timestamp": timestamp,
                "platform": "tiktok",
                "content_type": infer_content_type(video),
                "watch_time_seconds": extract_watch_time(video),
                "hashtags": extract_hashtags_from_text(video.get("caption", "") or video.get("Caption", "") or video.get("description", "")),
                "raw_data": dumps(video)
            }
            save_to_glue_path("videos", video_record, timestamp)
        
        # Extract comments
        comments = extract_comments(data)
        for i, comment in enumerate(comments):
            comment_record = {
                "upload_id": upload_id,
                "comment_id": f"{upload_id}_c_{i}",
                "timestamp": timestamp,
                "platform": "tiktok",
                "text": comment.get("comment", ""),
                "hashtags": extract_hashtags_from_text(comment.get("comment", "")),
                "raw_data": dumps(comment)
            }
            save_to_glue_path("comments", comment_record, timestamp)
            
        print(f"Normalized {len(videos)} videos and {len(comments)} comments from {key}")
        
        # Process collective data for aggregation only for original uploads
        if key.startswith('collective/'):
            process_collective_aggregation(data, videos, comments)
        
        # Trigger Glue Crawler for real-time discovery
        if videos or comments:
            trigger_crawler()
        
    except Exception as e:
        print(f"Error normalizing upload: {str(e)}")
        raise

def extract_videos(data):
    videos = []
    for path in [("Video", "Videos", "Activity", "VideoList"), ("Video", "Videos", "VideoList"), ("Videos",), ("Activity", "VideoList")]:
        ref = data
        for p in path:
            if isinstance(ref, dict) and p in ref:
                ref = ref[p]
            else:
                ref = None
                break
        if ref and isinstance(ref, list):
            videos.extend(ref)
            break
    return videos

def extract_comments(data):
    return (data.get("Comment", {}).get("Comments", {}).get("CommentsList", []))

def infer_content_type(video):
    dur = extract_watch_time(video)
    if video.get("is_live") or video.get("Live"):
        return "live"
    if dur and dur < 30:
        return "short_form"
    if dur and dur >= 60:
        return "long_form"
    return "standard"

def extract_watch_time(video):
    for k in ("watch_time_seconds", "time_watched_seconds", "WatchTimeSeconds", "Watch time (s)", "duration", "Duration"):
        if k in video:
            try:
                return float(video[k])
            except (ValueError, TypeError) as e:
                print(f"Error converting {k} to float: {e}")
                continue
    return None

def extract_hashtags_from_text(text):
    return [m.lower() for m in HASHTAG_RE.findall(text or "")]

def save_to_glue_path(data_type, record, timestamp):
    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    year, month, day = dt.year, dt.month, dt.day
    
    glue_key = f"glue-data/{data_type}/year={year}/month={month:02d}/day={day:02d}/{record['upload_id']}_{record.get('video_id', record.get('comment_id', 'unknown'))}.json"
    
    s3.put_object(
        Bucket=BUCKET,
        Key=glue_key,
        Body=dumps(record),
        ContentType="application/json"
    )

def process_collective_aggregation(data, videos, comments):
    """Process collective data for DynamoDB aggregation"""
    try:
        # Aggregate hashtags from videos and comments
        for video in videos:
            caption = video.get("caption", "") or video.get("Caption", "") or video.get("description", "")
            for hashtag in extract_hashtags_from_text(caption):
                increment_stat("collective_hashtag", hashtag)
            
            # Aggregate content types
            content_type = infer_content_type(video)
            increment_stat("collective_content_type", content_type)
        
        for comment in comments:
            comment_text = comment.get("comment", "")
            for hashtag in extract_hashtags_from_text(comment_text):
                increment_stat("collective_hashtag", hashtag)
        
        # Aggregate watch time
        total_watch_time = sum(extract_watch_time(v) or 0 for v in videos)
        if total_watch_time > 0:
            add_watch_time(total_watch_time, len([v for v in videos if extract_watch_time(v)]))
            
    except Exception as e:
        print(f"Error in collective aggregation: {str(e)}")

def increment_stat(stat_type, period, count=1):
    """Increment a stat in DynamoDB"""
    try:
        # Validate inputs to prevent injection
        if not isinstance(stat_type, str) or not isinstance(period, str):
            raise ValueError("stat_type and period must be strings")
        if not isinstance(count, (int, float)) or count < 0:
            raise ValueError("count must be a non-negative number")
            
        table.update_item(
            Key={"stat_type": stat_type, "period": period},
            UpdateExpression="ADD #c :val SET last_updated = :now",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={
                ":val": count,
                ":now": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        )
    except Exception as e:
        print(f"Error incrementing stat {stat_type}/{period}: {str(e)}")

def add_watch_time(total_seconds, sample_count):
    """Add watch time data to DynamoDB"""
    try:
        # Validate inputs to prevent injection
        if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
            raise ValueError("total_seconds must be a non-negative number")
        if not isinstance(sample_count, int) or sample_count < 0:
            raise ValueError("sample_count must be a non-negative integer")
            
        table.update_item(
            Key={"stat_type": "collective_watchtime", "period": "TOTAL"},
            UpdateExpression="ADD sum_seconds :sec, sample_count :count SET last_updated = :now",
            ExpressionAttributeValues={
                ":sec": total_seconds,
                ":count": sample_count,
                ":now": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        )
    except Exception as e:
        print(f"Error adding watch time: {str(e)}")

def trigger_crawler():
    """Trigger Glue Crawler to discover new partitions immediately"""
    try:
        response = glue.start_crawler(Name=CRAWLER_NAME)
        print(f"Triggered crawler {CRAWLER_NAME}")
    except glue.exceptions.CrawlerRunningException:
        print(f"Crawler {CRAWLER_NAME} already running")
    except Exception as e:
        print(f"Error triggering crawler: {str(e)}")

def handler(event, context):
    """Process S3 upload events and normalize data for Glue Catalog"""
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        
        # Only process original uploads, not normalized glue-data files
        if key.startswith('glue-data/'):
            print(f"Skipping normalized file: {key}")
            continue
            
        if key.startswith('collective/') or 'anonymous' in key:
            normalize_upload_for_glue(bucket, key)
        else:
            print(f"Skipping private upload: {key}")
            
    return {"statusCode": 200, "body": "Processing complete"}

