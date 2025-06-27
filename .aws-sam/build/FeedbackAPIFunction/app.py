import json
import boto3
import os
import logging
from datetime import datetime
import uuid

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

dynamodb = boto3.resource('dynamodb')
feedback_table_name = os.environ.get('FEEDBACK_TABLE')
feedback_table = dynamodb.Table(feedback_table_name)

def lambda_handler(event, context):
    """API handler for feedback submission"""
    try:
        logger.info("Processing feedback submission")
        
        # Parse request body
        if event.get('body'):
            body = json.loads(event['body'])
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Missing request body'
                })
            }
        
        # Validate required fields
        required_fields = ['customer_id', 'facility_id', 'prediction_id', 'feedback_type', 'rating']
        missing_fields = [field for field in required_fields if field not in body]
        
        if missing_fields:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': f'Missing required fields: {missing_fields}'
                })
            }
        
        # Create feedback record
        feedback_record = {
            'id': str(uuid.uuid4()),
            'customer_id': body['customer_id'],
            'facility_id': body['facility_id'],
            'prediction_id': body['prediction_id'],
            'feedback_type': body['feedback_type'],  # 'accuracy', 'usefulness', 'general'
            'rating': int(body['rating']),  # 1-5 scale
            'comments': body.get('comments', ''),
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': body.get('user_id', 'anonymous')
        }
        
        # Add optional fields
        if 'product_id' in body:
            feedback_record['product_id'] = body['product_id']
        
        if 'actual_quantity' in body:
            feedback_record['actual_quantity'] = float(body['actual_quantity'])
        
        if 'predicted_quantity' in body:
            feedback_record['predicted_quantity'] = float(body['predicted_quantity'])
        
        # Store feedback in DynamoDB
        feedback_table.put_item(Item=feedback_record)
        
        logger.info(f"Feedback stored successfully: {feedback_record['id']}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'Feedback submitted successfully',
                'feedback_id': feedback_record['id']
            })
        }
        
    except Exception as e:
        logger.error(f"Error in feedback API: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e)
            })
        }
