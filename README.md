# HumanTone

HumanTone lets creators understand their social media data without writing code. Upload your TikTok export and the app stores it securely in S3, processes it with AWS Lambda and Glue, and surfaces trends through simple web pages.

Uploads from signed‑in users are stored in a private area so they can explore personal insights. Files uploaded while signed out are aggregated anonymously for community-wide statistics.

The infrastructure is defined using the AWS CDK and includes:

- **Amazon S3** for hosting the site and storing raw uploads
- **AWS Lambda** functions for generating presigned upload URLs and cleaning data
- **Amazon DynamoDB** and **AWS Glue** for aggregation
- **Amazon Cognito** for optional authentication
- **API Gateway** for the upload API

## Monetization Ideas

The project can be monetized with paid tiers that unlock advanced analytics, personal data exports, and API access. Free anonymous uploads help grow the collective insights, while subscribers receive deeper trend analysis and additional upload capacity.

## Development

```bash
pip install -r requirements-dev.txt -r requirements.txt
pytest -q
```
