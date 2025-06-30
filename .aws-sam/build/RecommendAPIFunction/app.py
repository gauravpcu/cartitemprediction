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
    """API handler for recommendations"""
    try:
        # Extract query parameters
        query_params = event.get('queryStringParameters') or {}
        customer_id = query_params.get('customerId')
        facility_id = query_params.get('facilityId')
        recommendation_type = query_params.get('type')

        if not customer_id or not facility_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'message': 'Missing required parameters: customerId and facilityId'
                })
            }

        # Prepare payload for enhanced predictions function
        payload = {
            'action': 'recommend',
            'customerId': customer_id,
            'facilityId': facility_id,
            'recommendation_type': recommendation_type
        }
        
        # Invoke enhanced predictions function
        response = lambda_client.invoke(
            FunctionName=enhance_function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )

        # Parse response
        response_payload = json.loads(response['Payload'].read().decode('utf-8'))

        # Ensure the body is a JSON string if it's a dict
        response_body = response_payload.get('body', '{}')
        if isinstance(response_body, dict):
            response_body = json.dumps(response_body)

        return {
            'statusCode': response_payload.get('statusCode', 200),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': response_body
        }

    except Exception as e:
        logger.error(f"Error in recommendation API: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': str(e)
            })
        }
