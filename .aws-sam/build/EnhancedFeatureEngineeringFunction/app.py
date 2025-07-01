import json
import boto3
import csv
import os
import logging
import urllib.parse
from datetime import datetime
import pandas as pd

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
            create_date = datetime.strptime(row['CreateDate'], '%m/%d/%y')
            row['OrderYear'] = create_date.year
            row['OrderMonth'] = create_date.month
            row['OrderDay'] = create_date.day
            row['OrderDayOfWeek'] = create_date.weekday()
            row['IsWeekend'] = 1 if create_date.weekday() >= 5 else 0
            row['Date'] = create_date.strftime('%Y-%m-%d')
            processed_data.append(row)
    
    return processed_data

def create_lookup_files(df):
    """Create product and customer-product lookup files"""
    # Product Lookup
    product_lookup = df[['ProductID', 'ProductDescription', 'ProductCategory']].drop_duplicates()
    product_lookup.rename(columns={'ProductDescription': 'ProductName', 'ProductCategory': 'CategoryName'}, inplace=True)
    product_lookup['vendorName'] = 'Vendor' + product_lookup['ProductID'].astype(str).str.replace('PROD', '')

    # Customer-Product Lookup
    customer_product_lookup = df.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg(
        OrderCount=('Quantity', 'count'),
        FirstOrderDate=('CreateDate', 'min'),
        LastOrderDate=('CreateDate', 'max')
    ).reset_index()

    # Merge with product details
    customer_product_lookup = pd.merge(customer_product_lookup, product_lookup, on='ProductID')
    
    return product_lookup, customer_product_lookup

def lambda_handler(event, context):
    """Lambda function handler to process S3 data and create lookups"""
    try:
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
        
        logger.info(f"Processing file {key} from bucket {bucket}")
        
        download_path = f'/tmp/{os.path.basename(key)}'
        s3_client.download_file(bucket, key, download_path)
        
        # Process data with pandas
        df = pd.read_csv(download_path)
        # Normalize column names: strip spaces, make consistent case
        df.columns = [col.strip().replace(' ', '').replace('_', '').title() for col in df.columns]
        # Try to match expected columns
        col_map = {
            'Customerid': 'CustomerID',
            'Facilityid': 'FacilityID',
            'Productid': 'ProductID',
            'Productdescription': 'ProductDescription',
            'Productcategory': 'ProductCategory',
            'Createdate': 'CreateDate',
            'Quantity': 'Quantity'
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
        df['CreateDate'] = pd.to_datetime(df['CreateDate'], format='%m/%d/%y')

        product_lookup_df, customer_product_lookup_df = create_lookup_files(df)
        
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        
        # Save and upload product lookup
        product_lookup_path = '/tmp/product_lookup.csv'
        product_lookup_df.to_csv(product_lookup_path, index=False)
        product_lookup_key = f'lookup/{timestamp}/product_lookup.csv'
        s3_client.upload_file(product_lookup_path, processed_bucket, product_lookup_key)
        
        # Save and upload customer-product lookup
        customer_product_lookup_path = '/tmp/customer_product_lookup.csv'
        customer_product_lookup_df.to_csv(customer_product_lookup_path, index=False)
        customer_product_lookup_key = f'lookup/{timestamp}/customer_product_lookup.csv'
        s3_client.upload_file(customer_product_lookup_path, processed_bucket, customer_product_lookup_key)

        logger.info(f"Successfully created and uploaded lookup files to s3://{processed_bucket}/lookup/{timestamp}/")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Lookup files created successfully',
                'location': f's3://{processed_bucket}/lookup/{timestamp}/',
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
