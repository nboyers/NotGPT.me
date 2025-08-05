import json
import boto3
import os
import datetime
import hashlib
import re
import random
import math
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from collections import Counter
    

quicksight = boto3.client('quicksight')
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
table = dynamodb.Table(os.environ['AGGREGATION_TABLE'])
ACCOUNT_ID = os.environ.get('AWS_ACCOUNT_ID', boto3.client('sts').get_caller_identity()['Account'])
HASHTAG_RE = re.compile(r"#(\w{2,50})")

def _safe_json(body:str):
    try:
        return json.loads(body)
    except Exception:
        return {}

def _get_user_id_from_s3obj(head):
    # 1) uploader id from metadata set by your API (best)
    md = head.get("Metadata", {}) or {}
    uploader = md.get("uploader-id") or md.get("x-amz-meta-uploader-id")
    if uploader:
        return uploader

    # 2) S3 owner principal id if available
    owner = head.get("Owner", {}).get("ID")
    if owner:
        return f"owner_{owner[:32]}"

    # 3) Fallback: hash the ETag + size as a pseudo-id (still stable per user if they always upload from same account+file mix)
    etag = head.get("ETag", "").strip('"')
    size = head.get("ContentLength", 0)
    h = hashlib.sha256(f"{etag}:{size}".encode()).hexdigest()
    return f"fallback_{h[:32]}"

def _inc(stat_type:str, period:str, attr:str="count", n:int=1, extra_sets:dict=None):
    expr = "ADD #a :n"
    names = {"#a": attr}
    vals = {":n": n}
    if extra_sets:
        set_parts = []
        for i,(k,v) in enumerate(extra_sets.items(), start=1):
            names[f"#s{i}"] = k
            vals[f":s{i}"] = v
            set_parts.append(f"#s{i} = :s{i}")
        expr = f"{expr} SET " + ", ".join(set_parts)
    table.update_item(
        Key={"stat_type": stat_type, "period": period},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=vals,
    )

def _add_watchtime(seconds:float, samples:int=1):
    if seconds <= 0 or samples <= 0:
        return
    # keep numeric attributes; use separate ADD for both sums
    table.update_item(
        Key={"stat_type": "collective_watchtime", "period": "TOTAL"},
        UpdateExpression="ADD sum_seconds :sec, sample_count :s SET last_updated = :now",
        ExpressionAttributeValues={
            ":sec": seconds,
            ":s": samples,
            ":now": datetime.datetime.now().isoformat(),
        },
    )

def _extract_hashtags_from_text(text:str):
    return [m.lower() for m in HASHTAG_RE.findall(text or "")]

def _infer_content_type(video):
    # very light heuristics; extend as your exports evolve
    dur = None
    for k in ("duration", "Duration", "time_watched_seconds", "watch_time_seconds"):
        if k in video:
            try:
                dur = float(video[k])
                break
            except Exception:
                pass
    if video.get("is_live") or video.get("Live") is True:
        return "live"
    if video.get("images_count", 0) and int(video.get("images_count", 0)) > 1:
        return "slideshow"
    if dur is not None:
        if dur < 30:
            return "short_form"
        if dur >= 60:
            return "long_form"
    return "unspecified"

def _process_offsite(data:dict):
    ot = (data.get("Ads and data", {})
             .get("Off TikTok Activity", {})
             .get("OffTikTokActivityDataList", []))
    for e in ot:
        src = e.get("Source")
        evt = e.get("Event")
        if src:
            _inc("collective_offsite_source", src, n=1, extra_sets={"last_updated": datetime.datetime.now().isoformat()})
        if evt:
            _inc("collective_offsite_event", evt, n=1, extra_sets={"last_updated": datetime.datetime.now().isoformat()})

def _process_comments(data:dict):
    clist = (data.get("Comment", {})
                .get("Comments", {})
                .get("CommentsList", []))
    # mine hashtags from comments
    for c in clist:
        txt = c.get("comment", "")
        for tag in _extract_hashtags_from_text(txt):
            _inc("collective_hashtag", tag, n=1)

def _process_videos_for_watchtime_and_types(data:dict):
    # Your export variants may place videos in several places; check common ones
    candidates = []
    for path in [
        ("Video", "Videos", "Activity", "VideoList"),
        ("Video", "Videos", "VideoList"),
        ("Videos",),
        ("Activity", "VideoList"),
    ]:
        ref = data
        ok = True
        for p in path:
            if isinstance(ref, dict) and p in ref:
                ref = ref[p]
            else:
                ok = False
                break
        if ok and isinstance(ref, list):
            candidates.extend(ref)

    total_seconds = 0.0
    samples = 0
    for v in candidates:
        # accept various watch time keys if present
        secs = None
        for k in ("watch_time_seconds","time_watched_seconds","WatchTimeSeconds","Watch time (s)"):
            if k in v:
                try:
                    secs = float(v[k])
                    break
                except Exception:
                    pass
        if secs is not None and secs > 0:
            total_seconds += secs
            samples += 1

        # content type counters
        ctype = _infer_content_type(v)
        _inc("collective_content_type", ctype, n=1)

        # hashtags from caption if present
        for cap_key in ("caption","Caption","description","text"):
            if cap_key in v and isinstance(v[cap_key], str):
                for tag in _extract_hashtags_from_text(v[cap_key]):
                    _inc("collective_hashtag", tag, n=1)

    if samples > 0:
        _add_watchtime(total_seconds, samples)

def process_collective_upload(bucket, key):
    """Process a collective upload for anonymous users"""
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        user_id = _get_user_id_from_s3obj(head)

        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8", errors="ignore")
        data = _safe_json(content)

        # 1) register unique user
        _inc("collective_user", user_id, attr="seen", n=1, extra_sets={"last_seen": datetime.datetime.now().isoformat()})

        # 2) generic upload counter by platform and day (you already had this)
        parts = key.split("/")
        platform = parts[1].split("=")[1] if len(parts) > 1 and "=" in parts[1] else "unknown"
        _inc("collective_"+platform, datetime.datetime.now().strftime("%Y-%m-%d"), attr="upload_count", n=1, extra_sets={"last_updated": datetime.datetime.now().isoformat()})

        # 3) offsite tracking aggregations
        _process_offsite(data)

        # 4) comments → hashtags
        _process_comments(data)

        # 5) videos → watchtime, content types, hashtags
        _process_videos_for_watchtime_and_types(data)

        print(f"Processed collective upload for platform {platform}, user {user_id}")

    except Exception as e:
        print(f"Error processing collective upload: {str(e)}")
        raise

# Call the processing function for collective uploads
if os.environ.get('UPLOAD_BUCKET'):
    # This will be triggered by S3 events in ProcessUserData Lambda
    pass


def _get_top_items(stat_type: str, limit: int = 5):
    """Return top items for a given stat_type sorted by count."""
    try:
        resp = table.query(KeyConditionExpression=Key("stat_type").eq(stat_type))
        items = resp.get("Items", [])
        items.sort(key=lambda x: int(x.get("count", 0)), reverse=True)
        return [{"title": i.get("period", ""), "count": int(i.get("count", 0))} for i in items[:limit]]
    except Exception:
        return []


def get_avg_watch_time():
    """Get real average watch time from DynamoDB"""
    try:
        resp = table.get_item(Key={"stat_type": "collective_watchtime", "period": "TOTAL"})
        item = resp.get("Item", {})
        sum_seconds = float(item.get("sum_seconds", 0))
        sample_count = int(item.get("sample_count", 0))
        return round(sum_seconds / sample_count, 1) if sample_count > 0 else 0
    except:
        return 0

def get_athena_insights():
    """Query S3 data for user-friendly social media insights"""
    
    try:
        bucket = os.environ['UPLOAD_BUCKET']
        
        # Get total file count first
        total_files = 0
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix='glue-data/comments/'):
            total_files += len(page.get('Contents', []))
        
        # Use reasonable sample size for performance
        sample_size = min(100, total_files)  # Sample up to 100 files
        
        # Random sampling across all files
        emoji_count = 0
        mention_count = 0
        total_comments = 0
        
        # Get random sample of files
        all_files = []
        for page in paginator.paginate(Bucket=bucket, Prefix='glue-data/comments/'):
            all_files.extend(page.get('Contents', []))
        
        if all_files and len(all_files) > 0:
            actual_sample_size = min(sample_size, len(all_files))
            sample_files = random.sample(all_files, actual_sample_size) if actual_sample_size > 0 else []
            
            for obj in sample_files:
                try:
                    file_obj = s3.get_object(Bucket=bucket, Key=obj['Key'])
                    data = json.loads(file_obj['Body'].read().decode('utf-8'))
                    text = data.get('text', '')
                    
                    # Count emojis (basic Unicode ranges)
                    emoji_count += len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', text))
                    
                    # Count @ mentions
                    if '@' in text:
                        mention_count += 1
                        
                    total_comments += 1
                except:
                    continue
        
        # Total files already calculated above
        pass
        
        # Calculate actual percentages instead of estimates
        emoji_percentage = (emoji_count / total_comments * 100) if total_comments > 0 else 0
        mention_percentage = (mention_count / total_comments * 100) if total_comments > 0 else 0
        
        trending_topics = [{"title": "🔥 Emoji Usage", "count": round(emoji_percentage, 1)}]
        content_categories = [{"title": "💬 Comments Analyzed", "count": total_files}]
        avg_watch_time = 0  # No video data available
        
        return trending_topics, content_categories, avg_watch_time, mention_percentage
        
    except Exception as e:
        print(f"Analysis error: {e}")
        return [], [], 0

def update_insights_cache():
    """Update cached insights data"""
    try:
        trending_topics, content_categories, avg_watch_time, mention_percentage = get_athena_insights()
        
        # Cache the results in DynamoDB
        cache_data = {
            "trending_topics": trending_topics,
            "content_categories": content_categories,
            "avg_watch_time": avg_watch_time,
            "mention_percentage": mention_percentage,
            "last_updated": datetime.datetime.now().isoformat()
        }
        
        table.put_item(
            Item={
                "stat_type": "insights_cache",
                "period": "current",
                "data": json.dumps(cache_data),
                "last_updated": datetime.datetime.now().isoformat()
            }
        )
        print("Insights cache updated successfully")
        
    except Exception as e:
        print(f"Error updating insights cache: {e}")

def get_cached_insights():
    """Get cached insights data"""
    try:
        resp = table.get_item(Key={"stat_type": "insights_cache", "period": "current"})
        if "Item" in resp:
            cached_data = json.loads(resp["Item"]["data"])
            return cached_data
    except Exception as e:
        print(f"Error getting cached insights: {e}")
    return None

def handler(event, context):
    """Handle both scheduled updates and HTTP requests"""
    
    # Check if this is a scheduled event (EventBridge)
    if "source" in event and event["source"] == "aws.events":
        # This is a scheduled update
        update_insights_cache()
        return {"statusCode": 200, "body": "Cache updated"}
    
    # This is an HTTP request - return cached data
    cached_data = get_cached_insights()
    
    if cached_data:
        # Use cached data
        trending_topics = cached_data["trending_topics"]
        content_categories = cached_data["content_categories"]
        avg_watch_time = cached_data["avg_watch_time"]
        mention_percentage = cached_data["mention_percentage"]
    else:
        # Fallback: generate data on-demand (first time or cache miss)
        try:
            trending_topics, content_categories, avg_watch_time, mention_percentage = get_athena_insights()
            # Update cache for next time
            update_insights_cache()
        except:
            # Final fallback to DynamoDB
            trending_topics = _get_top_items("collective_hashtag", 5)
            content_categories = _get_top_items("collective_content_type", 5)
            avg_watch_time = get_avg_watch_time()
            mention_percentage = 0
    
    top_hashtag = trending_topics[0] if trending_topics else {"title": "none", "count": 0}
    
    body = {
        "trending_topics": trending_topics,
        "content_categories": content_categories,
        "stats": {"avg_watch_time": avg_watch_time},
        "quicksight_urls": get_quicksight_urls(),
        "insights": [{
            "title": f"🔥 {top_hashtag['title']}",
            "description": "Percentage of comments containing emojis",
            "metric": f"{top_hashtag['count']}% with emojis"
        }, {
            "title": "👥 Social Mentions",
            "description": "Comments with @ mentions to other users",
            "metric": f"{mention_percentage}% mention others"
        }]
    }
    
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json", 
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        },
        "body": json.dumps(body, default=str)
    }

def get_quicksight_urls():
    """Generate QuickSight embed URLs for dashboards"""
    try:
        # Create a simple dashboard URL for comment analytics
        # For now, return None to use Chart.js with real Athena data
        return {
            "trending": None,  # Will use Chart.js with Athena data
            "categories": None  # Will use Chart.js with Athena data
        }
    except Exception as e:
        print(f"QuickSight error: {e}")
        return {"trending": None, "categories": None}


