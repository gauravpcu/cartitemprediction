import json
import os
import logging
import uuid
from datetime import datetime

# Import layer dependencies with error handling
try:
    import boto3
except ImportError as e:
    logging.error(f"Failed to import boto3 from AWSUtilitiesLayer: {e}")
    raise

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

dynamodb = boto3.resource('dynamodb')
feedback_table_name = os.environ.get('FEEDBACK_TABLE')

def format_error_response(status_code, message, error_code=None):
    """Format error response matching notebook's error handling patterns"""
    error_response = {
        'error': True,
        'message': message,
        'timestamp': datetime.now().isoformat(),
        'statusCode': status_code
    }
    
    if error_code:
        error_response['errorCode'] = error_code
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': json.dumps(error_response)
    }

def format_success_response(data):
    """Format success response with consistent structure"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'POST,OPTIONS'
        },
        'body': json.dumps(data, default=str)
    }

def lambda_handler(event, context):
    """API handler for feedback submission with consistent error handling"""
    try:
        logger.info("Processing feedback submission")
        
        # Handle OPTIONS request for CORS
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': ''
            }
        
        # Validate DynamoDB table configuration
        if not feedback_table_name:
            logger.error("Feedback table name not configured")
            return format_error_response(
                503,
                'Feedback service not properly configured',
                'SERVICE_MISCONFIGURED'
            )
        
        try:
            feedback_table = dynamodb.Table(feedback_table_name)
        except Exception as table_error:
            logger.error(f"Failed to access feedback table: {str(table_error)}")
            return format_error_response(
                503,
                'Feedback service temporarily unavailable',
                'SERVICE_UNAVAILABLE'
            )
        
        # Parse request body
        if not event.get('body'):
            logger.error("Missing request body")
            return format_error_response(
                400,
                'Request body is required for feedback submission',
                'MISSING_BODY'
            )
        
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {str(e)}")
            return format_error_response(
                400,
                'Invalid JSON format in request body',
                'INVALID_JSON'
            )
        
        # Validate required fields
        required_fields = ['customer_id', 'facility_id', 'prediction_id', 'feedback_type', 'rating']
        missing_fields = [field for field in required_fields if field not in body or body[field] is None]
        
        if missing_fields:
            logger.error(f"Missing required fields: {missing_fields}")
            return format_error_response(
                400,
                f'Missing required fields: {", ".join(missing_fields)}',
                'MISSING_FIELDS'
            )
        
        # Validate field formats and values
        try:
            # Validate rating
            rating = int(body['rating'])
            if rating < 1 or rating > 5:
                raise ValueError("Rating must be between 1 and 5")
            
            # Validate feedback_type
            valid_feedback_types = ['accuracy', 'usefulness', 'general', 'recommendation']
            if body['feedback_type'] not in valid_feedback_types:
                raise ValueError(f"feedback_type must be one of: {', '.join(valid_feedback_types)}")
            
            # Validate customer_id and facility_id are not empty
            if not str(body['customer_id']).strip() or not str(body['facility_id']).strip():
                raise ValueError("customer_id and facility_id cannot be empty")
                
        except (ValueError, TypeError) as validation_error:
            logger.error(f"Field validation error: {str(validation_error)}")
            return format_error_response(
                400,
                f'Invalid field values: {str(validation_error)}',
                'INVALID_FIELD_VALUES'
            )
        
        # Create feedback record
        feedback_record = {
            'id': str(uuid.uuid4()),
            'customer_id': str(body['customer_id']).strip(),
            'facility_id': str(body['facility_id']).strip(),
            'prediction_id': str(body['prediction_id']).strip(),
            'feedback_type': body['feedback_type'],
            'rating': rating,
            'comments': body.get('comments', ''),
            'timestamp': datetime.utcnow().isoformat(),
            'user_id': body.get('user_id', 'anonymous')
        }
        
        # Add optional fields with validation
        if 'product_id' in body and body['product_id']:
            feedback_record['product_id'] = str(body['product_id']).strip()
        
        if 'actual_quantity' in body and body['actual_quantity'] is not None:
            try:
                feedback_record['actual_quantity'] = float(body['actual_quantity'])
                if feedback_record['actual_quantity'] < 0:
                    logger.warning("Negative actual_quantity provided")
            except (ValueError, TypeError):
                logger.warning(f"Invalid actual_quantity value: {body['actual_quantity']}")
        
        if 'predicted_quantity' in body and body['predicted_quantity'] is not None:
            try:
                feedback_record['predicted_quantity'] = float(body['predicted_quantity'])
                if feedback_record['predicted_quantity'] < 0:
                    logger.warning("Negative predicted_quantity provided")
            except (ValueError, TypeError):
                logger.warning(f"Invalid predicted_quantity value: {body['predicted_quantity']}")
        
        # Store feedback in DynamoDB
        try:
            feedback_table.put_item(Item=feedback_record)
            logger.info(f"Feedback stored successfully: {feedback_record['id']}")
        except Exception as db_error:
            logger.error(f"Failed to store feedback in DynamoDB: {str(db_error)}")
            return format_error_response(
                503,
                'Failed to store feedback. Please try again later.',
                'DATABASE_ERROR'
            )
        
        # Return success response
        response_data = {
            'success': True,
            'message': 'Feedback submitted successfully',
            'feedback_id': feedback_record['id'],
            'timestamp': feedback_record['timestamp']
        }
        
        return format_success_response(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error in feedback API: {str(e)}")
        return format_error_response(
            500,
            'Internal server error. Please contact support if the problem persists.',
            'INTERNAL_ERROR'
        )
