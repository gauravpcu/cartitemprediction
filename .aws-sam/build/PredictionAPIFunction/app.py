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
    
    # For aggregate predictions, we might need to transform the product-level data
    # into a summary format if that's what this endpoint is supposed to return
    if 'productPredictions' in data and 'summary' not in data:
        # Create summary from product predictions
        product_predictions = data['productPredictions']
        total_products = len(product_predictions)
        
        # Calculate aggregate metrics
        total_predicted_demand = 0
        high_confidence_products = 0
        
        for product in product_predictions:
            predictions = product.get('predictions', {})
            if predictions:
                # Sum up the mean predictions for the next few days
                daily_means = [day_pred.get('mean', 0) for day_pred in predictions.values()]
                total_predicted_demand += sum(daily_means[:7])  # Next 7 days
            
            # Count high confidence recommendations if available
            if 'recommendations' in data:
                for rec_product in data['recommendations'].get('recommended_products', []):
                    if rec_product.get('product_id') == product.get('product_id') and rec_product.get('confidence', 0) > 80:
                        high_confidence_products += 1
        
        data['summary'] = {
            'total_products_analyzed': total_products,
            'total_predicted_demand_7days': total_predicted_demand,
            'high_confidence_products': high_confidence_products,
            'prediction_period': '7 days'
        }
    
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
    """API handler for order predictions with consistent error handling"""
    try:
        logger.info("Processing prediction request")
        
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
            'facilityId': facility_id,
            'prediction_type': 'aggregate'  # This endpoint focuses on aggregate predictions
        }
        
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
        
        # Return formatted success response
        return format_success_response(response_body)
            
    except Exception as e:
        logger.error(f"Unexpected error in prediction API: {str(e)}")
        return format_error_response(
            500,
            'Internal server error. Please contact support if the problem persists.',
            'INTERNAL_ERROR'
        )
