#!/usr/bin/env python3
"""
Test script for the optimized feature engineering function
"""

import boto3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

def generate_large_test_data(num_rows=100000):
    """Generate a large test dataset to test memory optimization"""
    print(f"Generating {num_rows} rows of test data...")
    
    # Generate realistic data
    customers = [f"CUSTOMER_{i:04d}" for i in range(1, 51)]  # 50 customers
    facilities = list(range(1, 101))  # 100 facilities
    products = [f"PROD_{i:05d}" for i in range(1, 1001)]  # 1000 products
    categories = ["Medical", "Surgical", "Pharmacy", "Equipment", "Supplies"]
    
    data = []
    start_date = datetime(2024, 1, 1)
    
    for i in range(num_rows):
        # Generate realistic order data
        order_date = start_date + timedelta(days=random.randint(0, 365))
        
        row = {
            'PortalID': 'HYB',
            'CreateDate': order_date.strftime('%m/%d/%y'),
            'CustomerID': random.choice(customers),
            'FacilityID': random.choice(facilities),
            'ProductID': random.choice(products),
            'Quantity': random.randint(1, 20),
            'UnitPrice': round(random.uniform(1.0, 100.0), 2),
            'OrderID': f"ORD_{i:08d}",
            'CategoryName': random.choice(categories),
            'ProductName': f"Product {random.choice(products)}"
        }
        data.append(row)
        
        if (i + 1) % 10000 == 0:
            print(f"Generated {i + 1} rows...")
    
    df = pd.DataFrame(data)
    return df

def upload_test_data(df, bucket_name, file_name):
    """Upload test data to S3"""
    print(f"Uploading {len(df)} rows to S3...")
    
    # Save to local file first
    local_file = f"/tmp/{file_name}"
    df.to_csv(local_file, index=False)
    
    # Upload to S3
    s3_client = boto3.client('s3')
    try:
        s3_client.upload_file(local_file, bucket_name, file_name)
        print(f"Successfully uploaded {file_name} to {bucket_name}")
        
        # Clean up local file
        os.remove(local_file)
        
        return True
    except Exception as e:
        print(f"Error uploading file: {e}")
        return False

def monitor_lambda_execution(function_name, timeout_minutes=20):
    """Monitor Lambda function execution via CloudWatch logs"""
    import time
    
    logs_client = boto3.client('logs')
    log_group_name = f"/aws/lambda/{function_name}"
    
    print(f"Monitoring logs for {function_name}...")
    print("Waiting for execution to start...")
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Get recent log streams
            response = logs_client.describe_log_streams(
                logGroupName=log_group_name,
                orderBy='LastEventTime',
                descending=True,
                limit=5
            )
            
            if response['logStreams']:
                latest_stream = response['logStreams'][0]
                stream_name = latest_stream['logStreamName']
                
                # Get recent log events
                events_response = logs_client.get_log_events(
                    logGroupName=log_group_name,
                    logStreamName=stream_name,
                    startFromHead=False,
                    limit=50
                )
                
                # Print recent events
                for event in events_response['events'][-10:]:  # Last 10 events
                    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                    message = event['message'].strip()
                    if message and not message.startswith('START') and not message.startswith('END'):
                        print(f"[{timestamp.strftime('%H:%M:%S')}] {message}")
                
                # Check for completion or error
                recent_messages = [event['message'] for event in events_response['events'][-5:]]
                
                if any('Successfully processed' in msg for msg in recent_messages):
                    print("✅ Function completed successfully!")
                    return True
                elif any('Error processing file' in msg for msg in recent_messages):
                    print("❌ Function failed with error!")
                    return False
                elif any('Runtime.OutOfMemory' in msg for msg in recent_messages):
                    print("❌ Function ran out of memory!")
                    return False
                elif any('Task timed out' in msg for msg in recent_messages):
                    print("❌ Function timed out!")
                    return False
        
        except Exception as e:
            print(f"Error monitoring logs: {e}")
        
        time.sleep(10)  # Check every 10 seconds
    
    print("⏰ Monitoring timeout reached")
    return False

def main():
    """Main test function"""
    # Configuration
    bucket_name = "item-prediction-raw-data-dev-533267165065"
    function_name = "feature-engineering-dev"
    
    print("🧪 Testing Optimized Feature Engineering Function")
    print("=" * 50)
    
    # Test different data sizes
    test_sizes = [
        (10000, "small_test_data.csv"),
        (50000, "medium_test_data.csv"),
        (100000, "large_test_data.csv")
    ]
    
    for num_rows, file_name in test_sizes:
        print(f"\n📊 Testing with {num_rows} rows ({file_name})")
        print("-" * 40)
        
        # Generate test data
        df = generate_large_test_data(num_rows)
        
        # Upload to S3 (this will trigger the Lambda)
        if upload_test_data(df, bucket_name, file_name):
            # Monitor execution
            success = monitor_lambda_execution(function_name, timeout_minutes=20)
            
            if success:
                print(f"✅ Test with {num_rows} rows completed successfully!")
            else:
                print(f"❌ Test with {num_rows} rows failed!")
                break
        else:
            print(f"❌ Failed to upload test data for {num_rows} rows")
            break
        
        print("\nWaiting 30 seconds before next test...")
        import time
        time.sleep(30)
    
    print("\n🏁 Testing completed!")

if __name__ == "__main__":
    main()