import json
import os
import logging
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

lambda_client = boto3.client('lambda')
enhance_function_name = os.environ.get('ENHANCE_FUNCTION_NAME')

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
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(error_response)
    }

def format_success_response(data):
    """Format success response matching notebook's JSON structure"""
    # Ensure the response matches notebook's expected format
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            logger.error("Failed to parse response data as JSON")
            return format_error_response(500, "Invalid response format from prediction service")
    
    # Validate required fields matching notebook's structure
    required_fields = ['id', 'timestamp', 'customerId', 'facilityId', 'productPredictions']
    for field in required_fields:
        if field not in data:
            logger.warning(f"Missing required field in response: {field}")
    
    # Ensure productPredictions has the correct structure
    if 'productPredictions' in data:
        for product in data['productPredictions']:
            # Validate product prediction structure matches notebook format
            required_product_fields = ['product_id', 'product_name', 'predictions', 'order_history']
            for field in required_product_fields:
                if field not in product:
                    logger.warning(f"Missing required product field: {field}")
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,OPTIONS'
        },
        'body': json.dumps(data, default=str)  # default=str to handle datetime objects
    }

def lambda_handler(event, context):
    """API handler for product-level predictions matching notebook's JSON format"""
    try:
        logger.info("Processing product-level prediction request")
        
        # Handle OPTIONS request for CORS
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,OPTIONS'
                },
                'body': ''
            }
        
        # Extract query parameters
        query_params = event.get('queryStringParameters') or {}
        customer_id = query_params.get('customerId')
        facility_id = query_params.get('facilityId')

        # Validate required parameters
        if not customer_id or not facility_id:
            logger.error("Missing required parameters: customerId and facilityId")
            return format_error_response(
                400, 
                'Missing required parameters: customerId and facilityId',
                'MISSING_PARAMETERS'
            )

        # Validate parameter formats (basic validation)
        try:
            # Ensure customer_id and facility_id can be converted to strings
            customer_id = str(customer_id).strip()
            facility_id = str(facility_id).strip()
            
            if not customer_id or not facility_id:
                raise ValueError("Empty parameter values")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid parameter format: {str(e)}")
            return format_error_response(
                400,
                'Invalid parameter format. customerId and facilityId must be valid identifiers',
                'INVALID_PARAMETERS'
            )

        # Prepare payload for enhanced predictions function
        payload = {
            'customerId': customer_id,
            'facilityId': facility_id
        }
        
        # Optional product filter
        product_id = query_params.get('productId')
        if product_id:
            payload['productId'] = str(product_id).strip()
        
        logger.info(f"Invoking enhanced predictions function for customer {customer_id}, facility {facility_id}")
        
        # Invoke enhanced predictions function
        try:
            response = lambda_client.invoke(
                FunctionName=enhance_function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
        except Exception as invoke_error:
            logger.error(f"Failed to invoke enhanced predictions function: {str(invoke_error)}")
            return format_error_response(
                503,
                'Prediction service temporarily unavailable. Please try again later.',
                'SERVICE_UNAVAILABLE'
            )

        # Parse response
        try:
            response_payload = json.loads(response['Payload'].read().decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response from enhanced predictions function: {str(e)}")
            return format_error_response(
                502,
                'Invalid response from prediction service',
                'INVALID_SERVICE_RESPONSE'
            )

        # Handle error responses from the enhanced predictions function
        status_code = response_payload.get('statusCode', 200)
        if status_code != 200:
            error_body = response_payload.get('body', '{}')
            if isinstance(error_body, str):
                try:
                    error_data = json.loads(error_body)
                    error_message = error_data.get('message', 'Unknown error from prediction service')
                except json.JSONDecodeError:
                    error_message = error_body
            else:
                error_message = error_body.get('message', 'Unknown error from prediction service')
            
            logger.error(f"Enhanced predictions function returned error: {error_message}")
            return format_error_response(status_code, error_message, 'PREDICTION_SERVICE_ERROR')

        # Extract and format the response body
        response_body = response_payload.get('body', '{}')
        
        # Return formatted success response matching notebook's JSON structure
        return format_success_response(response_body)

    except Exception as e:
        logger.error(f"Unexpected error in product prediction API: {str(e)}")
        return format_error_response(
            500,
            'Internal server error. Please contact support if the problem persists.',
            'INTERNAL_ERROR'
        )
