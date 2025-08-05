import boto3
import json
import os

def create_quicksight_dashboards():
    """Create QuickSight data sources and dashboards for HumanTone analytics"""
    
    quicksight = boto3.client('quicksight')
    account_id = boto3.client('sts').get_caller_identity()['Account']
    
    # 1. Create Athena data source
    try:
        quicksight.create_data_source(
            AwsAccountId=account_id,
            DataSourceId='humantone-athena-source',
            Name='HumanTone Athena Data',
            Type='ATHENA',
            DataSourceParameters={
                'AthenaParameters': {
                    'WorkGroup': 'primary'
                }
            },
            Permissions=[{
                'Principal': f'arn:aws:quicksight:us-east-1:{account_id}:user/default/admin',
                'Actions': [
                    'quicksight:DescribeDataSource',
                    'quicksight:DescribeDataSourcePermissions',
                    'quicksight:PassDataSource',
                    'quicksight:UpdateDataSource',
                    'quicksight:DeleteDataSource',
                    'quicksight:UpdateDataSourcePermissions'
                ]
            }]
        )
        print("✅ Created Athena data source")
    except quicksight.exceptions.ResourceExistsException:
        print("ℹ️ Athena data source already exists")
    
    # 2. Create dataset for trending hashtags
    try:
        quicksight.create_data_set(
            AwsAccountId=account_id,
            DataSetId='trending-hashtags',
            Name='Trending Hashtags',
            PhysicalTableMap={
                'hashtags-table': {
                    'RelationalTable': {
                        'DataSourceArn': f'arn:aws:quicksight:us-east-1:{account_id}:datasource/humantone-athena-source',
                        'Catalog': 'AwsDataCatalog',
                        'Schema': 'humantone_user_data',
                        'Name': 'comments',
                        'InputColumns': [
                            {'Name': 'hashtags', 'Type': 'STRING'},
                            {'Name': 'timestamp', 'Type': 'DATETIME'},
                            {'Name': 'year', 'Type': 'STRING'},
                            {'Name': 'month', 'Type': 'STRING'},
                            {'Name': 'day', 'Type': 'STRING'}
                        ]
                    }
                }
            },
            ImportMode='DIRECT_QUERY'
        )
        print("✅ Created trending hashtags dataset")
    except quicksight.exceptions.ResourceExistsException:
        print("ℹ️ Trending hashtags dataset already exists")
    
    # 3. Create dataset for content categories
    try:
        quicksight.create_data_set(
            AwsAccountId=account_id,
            DataSetId='content-categories',
            Name='Content Categories',
            PhysicalTableMap={
                'videos-table': {
                    'RelationalTable': {
                        'DataSourceArn': f'arn:aws:quicksight:us-east-1:{account_id}:datasource/humantone-athena-source',
                        'Catalog': 'AwsDataCatalog',
                        'Schema': 'humantone_user_data',
                        'Name': 'videos',
                        'InputColumns': [
                            {'Name': 'content_type', 'Type': 'STRING'},
                            {'Name': 'watch_time_seconds', 'Type': 'DECIMAL'},
                            {'Name': 'timestamp', 'Type': 'DATETIME'},
                            {'Name': 'year', 'Type': 'STRING'},
                            {'Name': 'month', 'Type': 'STRING'},
                            {'Name': 'day', 'Type': 'STRING'}
                        ]
                    }
                }
            },
            ImportMode='DIRECT_QUERY'
        )
        print("✅ Created content categories dataset")
    except quicksight.exceptions.ResourceExistsException:
        print("ℹ️ Content categories dataset already exists")

if __name__ == "__main__":
    create_quicksight_dashboards()