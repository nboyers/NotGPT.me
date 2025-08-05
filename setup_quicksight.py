#!/usr/bin/env python3
"""
QuickSight setup script for HumanTone analytics
Run this once to create QuickSight data sources and dashboards
"""

import boto3
import json
import sys

def setup_quicksight():
    quicksight = boto3.client('quicksight')
    account_id = boto3.client('sts').get_caller_identity()['Account']
    
    print(f"Setting up QuickSight for account: {account_id}")
    
    # 1. Create Athena data source
    try:
        response = quicksight.create_data_source(
            AwsAccountId=account_id,
            DataSourceId='humantone-athena',
            Name='HumanTone Athena Data',
            Type='ATHENA',
            DataSourceParameters={
                'AthenaParameters': {
                    'WorkGroup': 'primary'
                }
            },
            Permissions=[{
                'Principal': f'arn:aws:quicksight:us-east-1:{account_id}:user/default/NobosDev',
                'Actions': [
                    'quicksight:DescribeDataSource',
                    'quicksight:DescribeDataSourcePermissions',
                    'quicksight:PassDataSource'
                ]
            }]
        )
        print("✅ Created Athena data source")
    except quicksight.exceptions.ResourceExistsException:
        print("ℹ️ Athena data source already exists")
    except Exception as e:
        print(f"❌ Error creating data source: {e}")
        return False
    
    # 2. Create dataset for comments
    try:
        response = quicksight.create_data_set(
            AwsAccountId=account_id,
            DataSetId='humantone-comments',
            Name='HumanTone Comments',
            PhysicalTableMap={
                'comments': {
                    'RelationalTable': {
                        'DataSourceArn': f'arn:aws:quicksight:us-east-1:{account_id}:datasource/humantone-athena',
                        'Catalog': 'AwsDataCatalog',
                        'Schema': 'humantone_user_data',
                        'Name': 'glue_data',
                        'InputColumns': [
                            {'Name': 'upload_id', 'Type': 'STRING'},
                            {'Name': 'comment_id', 'Type': 'STRING'},
                            {'Name': 'timestamp', 'Type': 'DATETIME'},
                            {'Name': 'platform', 'Type': 'STRING'},
                            {'Name': 'text', 'Type': 'STRING'},
                            {'Name': 'hashtags', 'Type': 'STRING'},
                            {'Name': 'raw_data', 'Type': 'STRING'}
                        ]
                    }
                }
            },
            ImportMode='DIRECT_QUERY',
            Permissions=[{
                'Principal': f'arn:aws:quicksight:us-east-1:{account_id}:user/default/NobosDev',
                'Actions': [
                    'quicksight:DescribeDataSet',
                    'quicksight:DescribeDataSetPermissions',
                    'quicksight:PassDataSet',
                    'quicksight:DescribeIngestion',
                    'quicksight:ListIngestions'
                ]
            }]
        )
        print("✅ Created comments dataset")
    except quicksight.exceptions.ResourceExistsException:
        print("ℹ️ Comments dataset already exists")
    except Exception as e:
        print(f"❌ Error creating dataset: {e}")
        return False
    
    # 3. Create analysis
    try:
        response = quicksight.create_analysis(
            AwsAccountId=account_id,
            AnalysisId='humantone-analysis',
            Name='HumanTone Comment Analysis',
            Definition={
                'DataSetIdentifierDeclarations': [{
                    'DataSetArn': f'arn:aws:quicksight:us-east-1:{account_id}:dataset/humantone-comments',
                    'Identifier': 'comments'
                }],
                'Sheets': [{
                    'SheetId': 'sheet1',
                    'Name': 'Comment Analytics',
                    'Visuals': [{
                        'BarChartVisual': {
                            'VisualId': 'comments-by-platform',
                            'Title': {'Visibility': 'VISIBLE', 'FormatText': {'PlainText': 'Comments by Platform'}},
                            'FieldWells': {
                                'BarChartAggregatedFieldWells': {
                                    'Category': [{'CategoricalDimensionField': {'FieldId': 'platform', 'Column': {'DataSetIdentifier': 'comments', 'ColumnName': 'platform'}}}],
                                    'Values': [{'NumericalMeasureField': {'FieldId': 'count', 'Column': {'DataSetIdentifier': 'comments', 'ColumnName': 'comment_id'}, 'AggregationFunction': {'SimpleNumericalAggregation': 'COUNT'}}}]
                                }
                            }
                        }
                    }]
                }]
            },
            Permissions=[{
                'Principal': f'arn:aws:quicksight:us-east-1:{account_id}:user/default/NobosDev',
                'Actions': [
                    'quicksight:RestoreAnalysis',
                    'quicksight:UpdateAnalysisPermissions',
                    'quicksight:DeleteAnalysis',
                    'quicksight:DescribeAnalysisPermissions',
                    'quicksight:QueryAnalysis',
                    'quicksight:DescribeAnalysis',
                    'quicksight:UpdateAnalysis'
                ]
            }]
        )
        print("✅ Created analysis")
    except quicksight.exceptions.ResourceExistsException:
        print("ℹ️ Analysis already exists")
    except Exception as e:
        print(f"❌ Error creating analysis: {e}")
        return False
    
    print("🎉 QuickSight setup complete!")
    print(f"📊 Access your analysis at: https://us-east-1.quicksight.aws.amazon.com/sn/analyses/humantone-analysis")
    return True

if __name__ == "__main__":
    success = setup_quicksight()
    sys.exit(0 if success else 1)