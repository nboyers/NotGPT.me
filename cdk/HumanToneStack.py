from aws_cdk import (
    Stack,
    RemovalPolicy,
    Tags,
    Duration,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_dynamodb as dynamodb,
    aws_s3_notifications as s3n,
    aws_glue as glue,
    aws_cognito as cognito,
    aws_apigateway as apigateway,
    aws_cloudfront as cloudfront,
    aws_cloudfront as cf,
    aws_iam as iam,
    aws_wafv2 as wafv2,
    aws_s3_deployment as s3deploy,
    aws_cloudfront_origins as origins,
    aws_events as events,
    aws_events_targets as targets,
    CfnOutput,
)
from aws_cdk.aws_lambda import Architecture
from constructs import Construct


class HumanToneStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cost_tags = {"Project": "HumanTone", "Environment": "production"}

        # ------------------------ FRONTEND ------------------------

        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )
        Tags.of(site_bucket).add("Project", cost_tags["Project"])

        oac = cloudfront.CfnOriginAccessControl(
            self,
            "SiteOAC",
            origin_access_control_config={
                "name": "S3-OAC",
                "description": "OAC for S3 access",
                "signingProtocol": "sigv4",
                "signingBehavior": "always",
                "originAccessControlOriginType": "s3",
            },
        )

        site_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[site_bucket.arn_for_objects("*")],
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                conditions={
                    "StringEquals": {
                        "AWS:SourceArn": f"arn:aws:cloudfront::{self.account}:distribution/*"
                    }
                },
            )
        )

        geo_origin_policy = cloudfront.CfnOriginRequestPolicy(
            self,
            "GeoHeaderPolicy",
            origin_request_policy_config={
                "name": "IncludeGeoHeaders",
                "comment": "Forward geo headers for region tracking",
                "headersConfig": {
                    "headerBehavior": "whitelist",
                    "headers": [
                        "CloudFront-Viewer-Country",
                        "CloudFront-Viewer-Country-Region",
                    ],
                },
                "cookiesConfig": {"cookieBehavior": "none"},
                "queryStringsConfig": {"queryStringBehavior": "none"},
            },
        )

        cf_dist = cf.CfnDistribution(
            self,
            "SiteDistribution",
            distribution_config={
                "enabled": True,
                "defaultRootObject": "index.html",
                "origins": [
                    {
                        "id": "S3Origin",
                        "domainName": site_bucket.bucket_regional_domain_name,
                        "originAccessControlId": oac.ref,
                        "s3OriginConfig": {},
                    }
                ],
                "defaultCacheBehavior": {
                    "targetOriginId": "S3Origin",
                    "viewerProtocolPolicy": "redirect-to-https",
                    "allowedMethods": ["GET", "HEAD"],
                    "cachedMethods": ["GET", "HEAD"],
                    "cachePolicyId": cloudfront.CachePolicy.CACHING_OPTIMIZED.cache_policy_id,
                    "originRequestPolicyId": geo_origin_policy.ref,
                    "compress": True,
                },
                "viewerCertificate": {"cloudFrontDefaultCertificate": True},
                "customErrorResponses": [
                    {
                        "errorCode": 403,
                        "responseCode": 200,
                        "responsePagePath": "/index.html",
                        "errorCachingMinTtl": 10,
                    },
                    {
                        "errorCode": 404,
                        "responseCode": 200,
                        "responsePagePath": "/index.html",
                        "errorCachingMinTtl": 10,
                    },
                ],
            },
        )

        s3deploy.BucketDeployment(
            self,
            "DeployWebsite",
            sources=[s3deploy.Source.asset("./site")],
            destination_bucket=site_bucket,
            retain_on_delete=False,
        )

        # ------------------------ AUTH ------------------------

        user_table = dynamodb.Table(
            self,
            "UserData",
            partition_key=dynamodb.Attribute(
                name="userId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        post_signup_lambda = _lambda.Function(
            self,
            "PostSignupLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="PostSignupLambda.handler",
            code=_lambda.Code.from_asset("lambda/post_signup"),
            memory_size=128,  # Minimal for simple DynamoDB writes
            timeout=Duration.seconds(5),
            environment={"USER_TABLE_NAME": user_table.table_name},
        )
        user_table.grant_write_data(post_signup_lambda)

        user_pool = cognito.UserPool(
            self,
            "UserPool6BA7E5F2-yp4TuYHz9RAa",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            lambda_triggers=cognito.UserPoolTriggers(
                post_confirmation=post_signup_lambda
            ),
        )

        user_client = user_pool.add_client(
            "FrontendClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
        )

        # ------------------------ INGESTION & ANALYTICS ------------------------

        upload_bucket = s3.Bucket(
            self,
            "UserUploadBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["https://humantone.me", "http://localhost:3000"],
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
        )
        Tags.of(upload_bucket).add("Project", cost_tags["Project"])

        aggregation_table = dynamodb.Table(
            self,
            "AggregateStatsTable",
            partition_key=dynamodb.Attribute(
                name="stat_type", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="period", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        Tags.of(aggregation_table).add("Project", cost_tags["Project"])

        get_url_function = _lambda.Function(
            self,
            "GetUploadUrl",
            runtime=_lambda.Runtime.PYTHON_3_13,
            architecture=Architecture.ARM_64,
            handler="GetUploadUrl.handler",
            code=_lambda.Code.from_asset("lambda/get_upload_url"),
            memory_size=128,  # Minimal for presigned URL generation
            timeout=Duration.seconds(5),
            environment={"UPLOAD_BUCKET": upload_bucket.bucket_name},
        )

        process_function = _lambda.Function(
            self,
            "ProcessUserData",
            runtime=_lambda.Runtime.PYTHON_3_13,
            architecture=Architecture.ARM_64,
            handler="ProcessUserData.handler",
            code=_lambda.Code.from_asset("lambda/data-cleaner"),
            memory_size=512,  # Optimized from power tuning
            timeout=Duration.seconds(30),  # Reduced from default
            environment={
                "AGGREGATION_TABLE": aggregation_table.table_name,
                "UPLOAD_BUCKET": upload_bucket.bucket_name,
                "CRAWLER_NAME": "HumanToneStack-DataCrawler",
            },
        )

        upload_bucket.grant_put(get_url_function)
        upload_bucket.grant_read_write(process_function)
        aggregation_table.grant_write_data(process_function)

        # Grant Glue permissions to ProcessUserData Lambda
        process_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["glue:StartCrawler"],
                resources=[f"arn:aws:glue:{self.region}:{self.account}:crawler/*"],
            )
        )

        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED, s3n.LambdaDestination(process_function)
        )

        api = apigateway.RestApi(
            self,
            "UploadApi",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"], allow_methods=["POST", "OPTIONS"]
            ),
        )
        api_resource = api.root.add_resource("api")
        presigned_resource = api_resource.add_resource("get-presigned-url")
        presigned_resource.add_method(
            "POST", apigateway.LambdaIntegration(get_url_function)
        )

        insights_function = _lambda.Function(
            self,
            "GetInsights",
            runtime=_lambda.Runtime.PYTHON_3_13,
            architecture=Architecture.ARM_64,
            handler="GetInsights.handler",
            code=_lambda.Code.from_asset("lambda/get_insights"),
            memory_size=128,  # Increased for data processing
            timeout=Duration.seconds(60),  # Increased for S3 sampling
            environment={
                "UPLOAD_BUCKET": upload_bucket.bucket_name,
                "GLUE_DATABASE": "humantone_user_data",
                "AWS_ACCOUNT_ID": self.account,
                "AGGREGATION_TABLE": aggregation_table.table_name,
                "INSIGHTS_CACHE_TABLE": aggregation_table.table_name,
            },
        )

        upload_bucket.grant_read_write(insights_function)
        aggregation_table.grant_read_write_data(insights_function)

        # Lifecycle policy to reduce storage costs
        upload_bucket.add_lifecycle_rule(
            id="DataLifecycle",
            prefix="collective/",  # Only raw uploads
            transitions=[
                s3.Transition(
                    storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                    transition_after=Duration.days(30),
                ),
                s3.Transition(
                    storage_class=s3.StorageClass.GLACIER,
                    transition_after=Duration.days(90),
                ),
            ],
        )

        # Keep processed data accessible for insights
        upload_bucket.add_lifecycle_rule(
            id="ProcessedDataLifecycle",
            prefix="glue-data/",
            transitions=[
                s3.Transition(
                    storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                    transition_after=Duration.days(
                        30
                    ),  # Minimum 30 days for Standard-IA
                )
            ],
        )

        # Add Athena and QuickSight permissions
        insights_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "athena:*",
                    "glue:GetTable",
                    "glue:GetPartitions",
                    "quicksight:GenerateEmbedUrlForAnonymousUser",
                ],
                resources=["*"],
            )
        )

        insights_resource = api_resource.add_resource("get-insights")
        insights_resource.add_method(
            "GET", apigateway.LambdaIntegration(insights_function)
        )

        # EventBridge rule to trigger insights update every 15 minutes

        insights_schedule = events.Rule(
            self,
            "InsightsSchedule",
            schedule=events.Schedule.rate(Duration.minutes(30)),  # Reduced frequency
        )
        insights_schedule.add_target(targets.LambdaFunction(insights_function))

        glue_db = glue.CfnDatabase(
            self,
            "UserDataDB",
            catalog_id=self.account,
            database_input={"name": "humantone_user_data"},
        )

        # Create Glue table for collective data
        glue_table_collective = glue.CfnTable(
            self,
            "CollectiveUploadsTable",
            catalog_id=self.account,
            database_name=glue_db.ref,
            table_input={
                "name": "collective_uploads",
                "tableType": "EXTERNAL_TABLE",
                "parameters": {"classification": "json"},
                "storageDescriptor": {
                    "columns": [
                        {"name": "platform", "type": "string"},
                        {"name": "timestamp", "type": "string"},
                        {"name": "event", "type": "string"},
                        {"name": "raw", "type": "string"},
                    ],
                    "location": f"s3://{upload_bucket.bucket_name}/collective/",
                    "inputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                    "outputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    "serdeInfo": {
                        "serializationLibrary": "org.openx.data.jsonserde.JsonSerDe",
                        "parameters": {},
                    },
                },
            },
        )

        # Create Glue tables for normalized data
        glue_table_videos = glue.CfnTable(
            self,
            "VideosTable",
            catalog_id=self.account,
            database_name=glue_db.ref,
            table_input={
                "name": "videos",
                "tableType": "EXTERNAL_TABLE",
                "parameters": {"classification": "json"},
                "partitionKeys": [
                    {"name": "year", "type": "string"},
                    {"name": "month", "type": "string"},
                    {"name": "day", "type": "string"},
                ],
                "storageDescriptor": {
                    "columns": [
                        {"name": "upload_id", "type": "string"},
                        {"name": "video_id", "type": "string"},
                        {"name": "timestamp", "type": "string"},
                        {"name": "platform", "type": "string"},
                        {"name": "content_type", "type": "string"},
                        {"name": "watch_time_seconds", "type": "double"},
                        {"name": "hashtags", "type": "array<string>"},
                        {"name": "raw_data", "type": "string"},
                    ],
                    "location": f"s3://{upload_bucket.bucket_name}/glue-data/videos/",
                    "inputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                    "outputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    "serdeInfo": {
                        "serializationLibrary": "org.openx.data.jsonserde.JsonSerDe"
                    },
                },
            },
        )

        glue_table_comments = glue.CfnTable(
            self,
            "CommentsTable",
            catalog_id=self.account,
            database_name=glue_db.ref,
            table_input={
                "name": "comments",
                "tableType": "EXTERNAL_TABLE",
                "parameters": {"classification": "json"},
                "partitionKeys": [
                    {"name": "year", "type": "string"},
                    {"name": "month", "type": "string"},
                    {"name": "day", "type": "string"},
                ],
                "storageDescriptor": {
                    "columns": [
                        {"name": "upload_id", "type": "string"},
                        {"name": "comment_id", "type": "string"},
                        {"name": "timestamp", "type": "string"},
                        {"name": "platform", "type": "string"},
                        {"name": "text", "type": "string"},
                        {"name": "hashtags", "type": "array<string>"},
                        {"name": "raw_data", "type": "string"},
                    ],
                    "location": f"s3://{upload_bucket.bucket_name}/glue-data/comments/",
                    "inputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                    "outputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    "serdeInfo": {
                        "serializationLibrary": "org.openx.data.jsonserde.JsonSerDe"
                    },
                },
            },
        )

        # Glue Crawler to discover partitions
        crawler_role = iam.Role(
            self,
            "GlueCrawlerRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSGlueServiceRole"
                )
            ],
        )
        upload_bucket.grant_read(crawler_role)

        glue_crawler = glue.CfnCrawler(
            self,
            "DataCrawler",
            role=crawler_role.role_arn,
            database_name=glue_db.ref,
            targets={
                "s3Targets": [{"path": f"s3://{upload_bucket.bucket_name}/glue-data/"}]
            },
            schedule={"scheduleExpression": "cron(0 2 * * ? *)"},  # Daily at 2 AM
        )

        # ------------------------ OUTPUTS ------------------------

        CfnOutput(self, "CloudFrontURL", value=f"https://{cf_dist.attr_domain_name}")
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_client.user_pool_client_id)
        CfnOutput(self, "UserTableName", value=user_table.table_name)
        CfnOutput(self, "UploadBucketName", value=upload_bucket.bucket_name)
        CfnOutput(self, "GlueDatabaseName", value=glue_db.ref)
        CfnOutput(self, "GlueVideosTableName", value="videos")
        CfnOutput(self, "GlueCommentsTableName", value="comments")
        CfnOutput(self, "ApiUrl", value=api.url)
