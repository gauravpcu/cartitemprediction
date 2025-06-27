import json
import boto3
import csv
from datetime import datetime, timedelta
import os
import logging
import urllib.parse
import math

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

s3_client = boto3.client('s3')
processed_bucket = os.environ.get('PROCESSED_BUCKET')

def process_csv_data(file_path):
    """Process CSV data without pandas"""
    logger.info("Processing CSV data...")
    
    processed_data = []
    with open(file_path, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Basic date processing
            create_date = datetime.strptime(row['CreateDate'], '%Y-%m-%d')
            row['OrderYear'] = create_date.year
            row['OrderMonth'] = create_date.month
            row['OrderDay'] = create_date.day
            row['OrderDayOfWeek'] = create_date.weekday()
            row['IsWeekend'] = 1 if create_date.weekday() >= 5 else 0
            row['Date'] = create_date.strftime('%Y-%m-%d')
            processed_data.append(row)
    
    return processed_data



def lambda_handler(event, context):
    """Simplified Lambda function handler"""
    try:
        # Get bucket and key from the S3 event
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
        
        logger.info(f"Processing file {key} from bucket {bucket}")
        
        # Download the file from S3
        download_path = '/tmp/order_data.csv'
        s3_client.download_file(bucket, key, download_path)
        
        # Process the data
        processed_data = process_csv_data(download_path)
        logger.info(f"Processed {len(processed_data)} rows of data")
        
        # Save processed data
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        processed_file = f'/tmp/processed_data_{timestamp}.csv'
        
        with open(processed_file, 'w', newline='') as file:
            if processed_data:
                writer = csv.DictWriter(file, fieldnames=processed_data[0].keys())
                writer.writeheader()
                writer.writerows(processed_data)
        
        processed_key = f'processed/{timestamp}/processed_data.csv'
        s3_client.upload_file(processed_file, processed_bucket, processed_key)
        
        logger.info(f"Successfully processed and uploaded data")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully processed {len(processed_data)} records',
                'processed_location': f's3://{processed_bucket}/{processed_key}'
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error processing file: {str(e)}'
            })
        }
