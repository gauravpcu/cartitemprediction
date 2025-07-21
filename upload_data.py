#!/usr/bin/env python3
"""
Simple data upload script for testing the optimized Lambda deployment
"""

import boto3
import sys
import os
from datetime import datetime

def upload_file_to_s3(file_path):
    """Upload a file to the raw data S3 bucket"""
    
    # S3 bucket from our deployment
    # Get bucket name dynamically from CloudFormation
    try:
        cf_client = boto3.client('cloudformation')
        stack_outputs = cf_client.describe_stacks(StackName='enhanced-order-prediction')['Stacks'][0]['Outputs']
        bucket_name = next(o['OutputValue'] for o in stack_outputs if o['OutputKey'] == 'RawDataBucketName')
    except:
        bucket_name = 'cart-prediction-rawdatabucket-6qnhmltcw42k'  # Fallback
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    try:
        s3_client = boto3.client('s3')
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        print(f"📤 Uploading {file_name} ({file_size / (1024*1024):.2f} MB) to S3...")
        
        # Upload the file
        s3_client.upload_file(file_path, bucket_name, file_name)
        
        print(f"✅ Successfully uploaded to s3://{bucket_name}/{file_name}")
        print(f"🔗 You can monitor processing in the AWS Console or CloudWatch logs")
        
        return True
        
    except Exception as e:
        print(f"❌ Error uploading file: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 upload_data.py <path_to_csv_file>")
        print("Example: python3 upload_data.py my_order_data.csv")
        sys.exit(1)
    
    file_path = sys.argv[1]
    success = upload_file_to_s3(file_path)
    
    if success:
        print("\n🎉 Upload completed! The Lambda functions will process this data automatically.")
        print("📊 Expected CSV format:")
        print("  Required columns: CreateDate, CustomerID, FacilityID, ProductID, Quantity")
        print("  Optional columns: UnitPrice, ProductCategory, ProductDescription")
    else:
        print("\n❌ Upload failed. Please check your file path and AWS credentials.")

if __name__ == "__main__":
    main()