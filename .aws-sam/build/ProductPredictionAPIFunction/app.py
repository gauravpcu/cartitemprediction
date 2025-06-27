import json
import boto3
import os
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

lambda_client = boto3.client('lambda')
enhance_function_name = os.environ.get('ENHANCE_FUNCTION_NAME')

def lambda_handler(event, context):
    """API handler for product-level predictions"""
    try:
        logger.info("Processing product-level prediction request")
        
        # Extract query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        customer_id = query_params.get('customerId')
        facility_id = query_params.get('facilityId')
        product_id = query_params.get('productId')  # Optional for specific product
        
        if not customer_id or not facility_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Missing required parameters: customerId and facilityId'
                })
            }
        
        # Prepare payload for enhanced predictions function
        payload = {
            'action': 'predict',
            'customer_id': customer_id,
            'facility_id': facility_id,
            'prediction_type': 'product_level'
        }
        
        if product_id:
            payload['product_id'] = product_id
        
        # Invoke enhanced predictions function
        response = lambda_client.invoke(
            FunctionName=enhance_function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        if response['StatusCode'] == 200:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(response_payload)
            }
        else:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Internal server error'
                })
            }
            
    except Exception as e:
        logger.error(f"Error in product prediction API: {str(e)}")
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
