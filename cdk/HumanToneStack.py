from aws_cdk import (
    Stack, RemovalPolicy, Tags, Duration,
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
    aws_cloudfront as cloudfront,
    CfnOutput
)
from aws_cdk.aws_lambda import Architecture
from constructs import Construct

class HumanToneStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cost_tags = {
            "Project": "HumanTone",
            "Environment": "production"
        }

        # ------------------------ FRONTEND ------------------------

        site_bucket = s3.Bucket(self, "SiteBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )
        Tags.of(site_bucket).add("Project", cost_tags["Project"])

        oac = cloudfront.CfnOriginAccessControl(self, "SiteOAC",
            origin_access_control_config={
                "name": "S3-OAC",
                "description": "OAC for S3 access",
                "signingProtocol": "sigv4",
                "signingBehavior": "always",
                "originAccessControlOriginType": "s3"
            }
        )

        site_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[site_bucket.arn_for_objects("*")],
            principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
            conditions={
                "StringEquals": {
                    "AWS:SourceArn": f"arn:aws:cloudfront::{self.account}:distribution/*"
                }
            }
        ))

        geo_origin_policy = cloudfront.CfnOriginRequestPolicy(self, "GeoHeaderPolicy",
            origin_request_policy_config={
                "name": "IncludeGeoHeaders",
                "comment": "Forward geo headers for region tracking",
                "headersConfig": {
                    "headerBehavior": "whitelist",
                    "headers": ["CloudFront-Viewer-Country", "CloudFront-Viewer-Country-Region"]
                },
                "cookiesConfig": {"cookieBehavior": "none"},
                "queryStringsConfig": {"queryStringBehavior": "none"}
            }
        )

        cf_dist = cf.CfnDistribution(self, "SiteDistribution",
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
                    "compress": True
                },
                "viewerCertificate": {
                    "cloudFrontDefaultCertificate": True
                }
            }
        )

        s3deploy.BucketDeployment(self, "DeployWebsite",
            sources=[s3deploy.Source.asset("./site")],
            destination_bucket=site_bucket,
            retain_on_delete=False
        )

        # ------------------------ AUTH ------------------------

        user_table = dynamodb.Table(self, "UserData",
            partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
        )

        post_signup_lambda = _lambda.Function(self, "PostSignupLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="PostSignupLambda.handler",
            code=_lambda.Code.from_asset("lambda/post_signup"),
            timeout=Duration.seconds(10),
            environment={
                "USER_TABLE_NAME": user_table.table_name
            }
        )
        user_table.grant_write_data(post_signup_lambda)

        user_pool = cognito.UserPool(self, "UserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            lambda_triggers=cognito.UserPoolTriggers(
                post_confirmation=post_signup_lambda
            )
        )

        user_client = user_pool.add_client("FrontendClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True)
        )

        # ------------------------ INGESTION & ANALYTICS ------------------------

        upload_bucket = s3.Bucket(self, "UserUploadBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )
        Tags.of(upload_bucket).add("Project", cost_tags["Project"])

        aggregation_table = dynamodb.Table(self, "AggregateStatsTable",
            partition_key={"name": "stat_type", "type": dynamodb.AttributeType.STRING},
            sort_key={"name": "period", "type": dynamodb.AttributeType.STRING},
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )
        Tags.of(aggregation_table).add("Project", cost_tags["Project"])

        process_function = _lambda.Function(self, "ProcessUserData",
            runtime=_lambda.Runtime.PYTHON_3_13,
            architecture=Architecture.ARM_64,
            handler="ProcessUserData.handler",
            code=_lambda.Code.from_asset("lambda/data-cleaner"),
            environment={
                "AGGREGATION_TABLE": aggregation_table.table_name,
                "UPLOAD_BUCKET": upload_bucket.bucket_name
            }
        )

        get_url_function = _lambda.Function(self, "GetUploadUrl",
            runtime=_lambda.Runtime.PYTHON_3_13,
            architecture=Architecture.ARM_64,
            handler="GetUploadUrl.handler",
            code=_lambda.Code.from_asset("lambda/get_upload_url"),
            environment={
                "UPLOAD_BUCKET": upload_bucket.bucket_name
            }
        )

        upload_bucket.grant_put(get_url_function)

        upload_bucket.grant_read(process_function)
        aggregation_table.grant_write_data(process_function)

        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(process_function)
        )

        api = apigateway.RestApi(self, "UploadApi",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["*"],
                allow_methods=["POST", "OPTIONS"]
            )
        )
        api_resource = api.root.add_resource("api").add_resource("get-presigned-url")
        api_resource.add_method("POST", apigateway.LambdaIntegration(get_url_function))

        glue_db = glue.CfnDatabase(self, "UserDataDB",
            catalog_id=self.account,
            database_input={"name": "humantone_user_data"}
        )

        glue_table = glue.CfnTable(self, "RawUploadsTable",
            catalog_id=self.account,
            database_name=glue_db.ref,
            table_input={
                "name": "uploads",
                "tableType": "EXTERNAL_TABLE",
                "parameters": {"classification": "json"},
                "storageDescriptor": {
                    "columns": [
                        {"name": "platform", "type": "string"},
                        {"name": "timestamp", "type": "string"},
                        {"name": "event", "type": "string"},
                        {"name": "raw", "type": "string"}
                    ],
                    "location": f"s3://{upload_bucket.bucket_name}/",
                    "inputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                    "outputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    "serdeInfo": {
                        "serializationLibrary": "org.openx.data.jsonserde.JsonSerDe",
                        "parameters": {}
                    }
                }
            }
        )

        # ------------------------ OUTPUTS ------------------------

        CfnOutput(self, "CloudFrontURL", value=f"https://{cf_dist.attr_domain_name}")
        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_client.user_pool_client_id)
        CfnOutput(self, "UserTableName", value=user_table.table_name)
        CfnOutput(self, "UploadBucketName", value=upload_bucket.bucket_name)
        CfnOutput(self, "GlueDatabaseName", value=glue_db.ref)
        CfnOutput(self, "GlueTableName", value="uploads")
        CfnOutput(self, "ApiUrl", value=api.url)
