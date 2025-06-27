import json
import boto3
import pandas as pd
import os
import logging
import urllib.parse

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

s3_client = boto3.client('s3')
processed_bucket = os.environ.get('PROCESSED_BUCKET')

def validate_data_quality(df):
    """Validate data quality and return validation results"""
    validation_results = {
        'is_valid': True,
        'issues': [],
        'warnings': [],
        'stats': {}
    }
    
    # Check for required columns
    required_columns = ['CreateDate', 'CustomerID', 'FacilityID', 'ProductID', 'Quantity']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        validation_results['is_valid'] = False
        validation_results['issues'].append(f"Missing required columns: {missing_columns}")
    
    # Check for null values in critical columns
    for col in required_columns:
        if col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                validation_results['warnings'].append(f"Column {col} has {null_count} null values")
    
    # Check date format
    if 'CreateDate' in df.columns:
        try:
            pd.to_datetime(df['CreateDate'])
        except Exception as e:
            validation_results['is_valid'] = False
            validation_results['issues'].append(f"Invalid date format in CreateDate: {str(e)}")
    
    # Check for negative quantities
    if 'Quantity' in df.columns:
        negative_qty = (df['Quantity'] < 0).sum()
        if negative_qty > 0:
            validation_results['warnings'].append(f"Found {negative_qty} records with negative quantities")
    
    # Basic statistics
    validation_results['stats'] = {
        'total_records': len(df),
        'date_range': {
            'start': str(df['CreateDate'].min()) if 'CreateDate' in df.columns else None,
            'end': str(df['CreateDate'].max()) if 'CreateDate' in df.columns else None
        },
        'unique_customers': df['CustomerID'].nunique() if 'CustomerID' in df.columns else 0,
        'unique_products': df['ProductID'].nunique() if 'ProductID' in df.columns else 0
    }
    
    return validation_results

def lambda_handler(event, context):
    """Lambda handler for data validation"""
    try:
        logger.info("Starting data validation process")
        
        # Parse S3 event
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            logger.info(f"Processing file: s3://{bucket}/{key}")
            
            # Read the processed data
            response = s3_client.get_object(Bucket=bucket, Key=key)
            df = pd.read_csv(response['Body'])
            
            # Validate data
            validation_results = validate_data_quality(df)
            
            # Save validation results
            validation_key = key.replace('processed/', 'validation/').replace('.csv', '_validation.json')
            
            s3_client.put_object(
                Bucket=processed_bucket,
                Key=validation_key,
                Body=json.dumps(validation_results, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Validation results saved to: s3://{processed_bucket}/{validation_key}")
            
            # If validation fails, create an alert
            if not validation_results['is_valid']:
                logger.error(f"Data validation failed for {key}: {validation_results['issues']}")
                # Here you could send SNS notification or create CloudWatch alarm
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Data validation completed successfully',
                'validation_results': validation_results
            })
        }
        
    except Exception as e:
        logger.error(f"Error in data validation: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
