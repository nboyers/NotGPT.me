# TikTok Analytics Platform Setup Guide

This guide walks through configuring AWS services for the landing page at `tiktok.html`.

## 1. Create the Cognito User Pool
1. Open the Amazon Cognito console and create a **User Pool** named `humantone-users`.
2. Enable email sign-up and choose a username alias such as email.
3. Under **Hosted UI**, enable the Hosted UI domain (e.g. `auth.humantone.me`).

## 2. Configure the App Client
1. In the User Pool, create an **App Client**.
2. Enable OAuth 2.0 authorization code grant or implicit grant.
3. Set callback URL to `https://humantone.me/tiktok.html` and logout URL to the same value.
4. Select scopes `openid`, `email`, and `profile`.
5. Note the client ID for use in `tiktok.js`.

## 3. S3 Bucket for Uploads
1. Create a bucket (e.g. `humantone-uploads`).
2. Configure CORS to allow `PUT` from `https://humantone.me`:
```xml
<CORSConfiguration>
  <CORSRule>
    <AllowedOrigin>https://humantone.me</AllowedOrigin>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
  </CORSRule>
</CORSConfiguration>
```
3. Restrict public access and enable server-side encryption as needed.

## 4. Lambda Function for Pre‑Signed URLs
1. Create a Lambda function (Python example) with permission to put objects in the upload bucket.
2. Attach an IAM policy allowing `s3:PutObject` on the bucket path.
3. The function returns a presigned URL for the given `user_id` and `file_name`.
```python
import json
import boto3
import os

def handler(event, context):
    body = json.loads(event["body"])
    user = body.get("user_id", "anonymous")
    key = f"uploads/{user}/{body['file_name']}"
    s3 = boto3.client('s3')
    url = s3.generate_presigned_url(
        ClientMethod='put_object',
        Params={'Bucket': os.environ['BUCKET'], 'Key': key},
        ExpiresIn=300,
    )
    return {
        'statusCode': 200,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({'url': url})
    }
```
4. Deploy this function behind API Gateway at `POST /get-presigned-url` and enable CORS.

## 5. Wire Up the Frontend
1. Update `tiktok.js` constants with your **CLIENT_ID**, **COGNITO_DOMAIN**, and **API_ENDPOINT**.
2. When a user selects a file and clicks upload, `tiktok.js` requests a presigned URL from the API and uploads the file directly to S3.
3. Logged-in users include their user ID (from the ID token) so files are stored privately. Anonymous users use the ID `anonymous` for collective data.

## 6. Testing
1. Navigate to `https://humantone.me/tiktok.html` and click **Sign In**. Authenticate through the Hosted UI and verify your email appears in the header.
2. Upload a file using the "Upload to My Account" button and confirm it appears under your user folder in S3.
3. Sign out and refresh the page. Only the Collective section should be visible.
4. Upload another file using the collective upload button and confirm it lands in the `anonymous` folder.
5. Use the question form in both states to ensure the note about data scope changes accordingly.
