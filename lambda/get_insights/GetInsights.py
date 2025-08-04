import boto3  # type: ignore
import os, json, datetime, hashlib, re
from urllib.parse import unquote_plus
from boto3.dynamodb.conditions import Key

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
BUCKET = os.environ["UPLOAD_BUCKET"]
AGGREGATION_TABLE = os.environ["AGGREGATION_TABLE"]
table = dynamodb.Table(AGGREGATION_TABLE)

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
