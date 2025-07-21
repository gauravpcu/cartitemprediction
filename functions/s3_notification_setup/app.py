import json
import logging

# Import layer dependencies with error handling
try:
    import boto3
    import urllib3
except ImportError as e:
    logging.error(f"Failed to import boto3/urllib3 from AWSUtilitiesLayer: {e}")
    raise

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

def send_response(event, context, response_status, response_data=None):
    """Send response to CloudFormation"""
    if response_data is None:
        response_data = {}
    
    response_url = event['ResponseURL']
    response_body = {
        'Status': response_status,
        'Reason': f'See CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }
    
    json_response_body = json.dumps(response_body)
    
    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }
    
    try:
        http = urllib3.PoolManager()
        response = http.request('PUT', response_url, body=json_response_body, headers=headers)
        logger.info(f"Status code: {response.status}")
    except Exception as e:
        logger.error(f"Failed to send response: {str(e)}")

def lambda_handler(event, context):
    """Handle S3 bucket notification setup"""
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        request_type = event['RequestType']
        properties = event['ResourceProperties']
        
        raw_bucket = properties['RawDataBucket']
        processed_bucket = properties['ProcessedDataBucket']
        feature_function = properties['FeatureEngineeringFunction']
        validation_function = properties['DataValidationFunction']
        
        if request_type == 'Create' or request_type == 'Update':
            # Set up notification for raw data bucket
            logger.info(f"Setting up notification for raw data bucket: {raw_bucket}")
            s3_client.put_bucket_notification_configuration(
                Bucket=raw_bucket,
                NotificationConfiguration={
                    'LambdaConfigurations': [
                        {
                            'Id': 'FeatureEngineeringTrigger',
                            'LambdaFunctionArn': feature_function,
                            'Events': ['s3:ObjectCreated:*'],
                            'Filter': {
                                'Key': {
                                    'FilterRules': [
                                        {
                                            'Name': 'suffix',
                                            'Value': '.csv'
                                        }
                                    ]
                                }
                            }
                        }
                    ]
                }
            )
            
            # Set up notification for processed data bucket
            logger.info(f"Setting up notification for processed data bucket: {processed_bucket}")
            s3_client.put_bucket_notification_configuration(
                Bucket=processed_bucket,
                NotificationConfiguration={
                    'LambdaConfigurations': [
                        {
                            'Id': 'DataValidationTrigger',
                            'LambdaFunctionArn': validation_function,
                            'Events': ['s3:ObjectCreated:*'],
                            'Filter': {
                                'Key': {
                                    'FilterRules': [
                                        {
                                            'Name': 'prefix',
                                            'Value': 'processed/'
                                        }
                                    ]
                                }
                            }
                        }
                    ]
                }
            )
            
            logger.info("S3 notifications configured successfully")
            send_response(event, context, 'SUCCESS')
            
        elif request_type == 'Delete':
            # Clean up notifications
            logger.info("Cleaning up S3 notifications")
            try:
                s3_client.put_bucket_notification_configuration(
                    Bucket=raw_bucket,
                    NotificationConfiguration={}
                )
                s3_client.put_bucket_notification_configuration(
                    Bucket=processed_bucket,
                    NotificationConfiguration={}
                )
            except Exception as e:
                logger.warning(f"Error cleaning up notifications: {str(e)}")
            
            send_response(event, context, 'SUCCESS')
        
    except Exception as e:
        logger.error(f"Error in S3 notification setup: {str(e)}")
        send_response(event, context, 'FAILED')
