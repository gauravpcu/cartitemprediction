#!/usr/bin/env python3

import json
import sys
import os

# Add the function directory to the path
sys.path.append('functions/enhanced_feature_engineering')

# Import the lambda function
from app import lambda_handler

# Create a test event that simulates an S3 trigger
test_event = {
    "Records": [
        {
            "s3": {
                "bucket": {
                    "name": "your-bucket-name"
                },
                "object": {
                    "key": "hybrent-0719.csv"
                }
            }
        }
    ]
}

# Mock context
class MockContext:
    def __init__(self):
        self.function_name = "test-function"
        self.function_version = "1"
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
        self.memory_limit_in_mb = "512"
        self.remaining_time_in_millis = lambda: 300000

if __name__ == "__main__":
    print("Testing lambda function with sample data...")
    
    # Set environment variables
    os.environ['PROCESSED_BUCKET'] = 'test-bucket'
    os.environ['PRODUCT_LOOKUP_TABLE'] = 'test-table'
    os.environ['LOG_LEVEL'] = 'DEBUG'
    
    try:
        context = MockContext()
        result = lambda_handler(test_event, context)
        print("Function executed successfully!")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()