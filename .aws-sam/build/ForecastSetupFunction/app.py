import json
import boto3
import os
import logging
from datetime import datetime
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

forecast_client = boto3.client('forecast')
s3_client = boto3.client('s3')
ssm_client = boto3.client('ssm')

forecast_role_arn = os.environ.get('FORECAST_ROLE_ARN')
processed_bucket = os.environ.get('PROCESSED_BUCKET')
enable_product_forecasting = os.environ.get('ENABLE_PRODUCT_FORECASTING', 'true').lower() == 'true'

def create_dataset_group(dataset_group_name):
    """Create a dataset group for forecasting"""
    try:
        response = forecast_client.create_dataset_group(
            DatasetGroupName=dataset_group_name,
            Domain='CUSTOM'
        )
        return response['DatasetGroupArn']
    except forecast_client.exceptions.ResourceAlreadyExistsException:
        # Dataset group already exists, get its ARN
        response = forecast_client.describe_dataset_group(
            DatasetGroupName=dataset_group_name
        )
        return response['DatasetGroupArn']

def create_dataset(dataset_name, dataset_group_arn):
    """Create a dataset for time series data"""
    try:
        schema = {
            'Attributes': [
                {'AttributeName': 'timestamp', 'AttributeType': 'timestamp'},
                {'AttributeName': 'target_value', 'AttributeType': 'float'},
                {'AttributeName': 'item_id', 'AttributeType': 'string'}
            ]
        }
        
        if enable_product_forecasting:
            # Add additional attributes for product-level forecasting
            schema['Attributes'].extend([
                {'AttributeName': 'customer_id', 'AttributeType': 'string'},
                {'AttributeName': 'facility_id', 'AttributeType': 'string'},
                {'AttributeName': 'product_category', 'AttributeType': 'string'}
            ])
        
        response = forecast_client.create_dataset(
            DatasetName=dataset_name,
            Domain='CUSTOM',
            DatasetType='TARGET_TIME_SERIES',
            DataFrequency='D',  # Daily frequency
            Schema=schema
        )
        
        # Add dataset to dataset group
        forecast_client.update_dataset_group(
            DatasetGroupArn=dataset_group_arn,
            DatasetArns=[response['DatasetArn']]
        )
        
        return response['DatasetArn']
        
    except forecast_client.exceptions.ResourceAlreadyExistsException:
        # Dataset already exists, get its ARN
        response = forecast_client.describe_dataset(
            DatasetName=dataset_name
        )
        return response['DatasetArn']

def create_dataset_import_job(dataset_arn, s3_path, job_name):
    """Create a dataset import job"""
    try:
        response = forecast_client.create_dataset_import_job(
            DatasetImportJobName=job_name,
            DatasetArn=dataset_arn,
            DataSource={
                'S3Config': {
                    'Path': s3_path,
                    'RoleArn': forecast_role_arn
                }
            }
        )
        return response['DatasetImportJobArn']
    except Exception as e:
        logger.error(f"Error creating dataset import job: {str(e)}")
        raise

def create_predictor(predictor_name, dataset_group_arn):
    """Create a predictor for forecasting"""
    try:
        forecast_horizon = 30  # Predict 30 days ahead
        
        predictor_config = {
            'PredictorName': predictor_name,
            'ForecastHorizon': forecast_horizon,
            'InputDataConfig': {
                'DatasetGroupArn': dataset_group_arn
            },
            'FeaturizationConfig': {
                'ForecastFrequency': 'D',
                'Featurizations': [
                    {
                        'AttributeName': 'target_value',
                        'FeaturizationPipeline': [
                            {
                                'FeaturizationMethodName': 'filling',
                                'FeaturizationMethodParameters': {
                                    'frontfill': 'none',
                                    'middlefill': 'zero',
                                    'backfill': 'zero'
                                }
                            }
                        ]
                    }
                ]
            }
        }
        
        if enable_product_forecasting:
            # Use AutoML for product-level forecasting
            predictor_config['PerformAutoML'] = True
        else:
            # Use specific algorithm for simpler forecasting
            predictor_config['AlgorithmArn'] = 'arn:aws:forecast:::algorithm/ARIMA'
        
        response = forecast_client.create_predictor(**predictor_config)
        return response['PredictorArn']
        
    except forecast_client.exceptions.ResourceAlreadyExistsException:
        # Predictor already exists, get its ARN
        response = forecast_client.describe_predictor(
            PredictorName=predictor_name
        )
        return response['PredictorArn']

def create_forecast(forecast_name, predictor_arn):
    """Create a forecast from the predictor"""
    try:
        response = forecast_client.create_forecast(
            ForecastName=forecast_name,
            PredictorArn=predictor_arn
        )
        return response['ForecastArn']
    except forecast_client.exceptions.ResourceAlreadyExistsException:
        # Forecast already exists, get its ARN
        response = forecast_client.describe_forecast(
            ForecastName=forecast_name
        )
        return response['ForecastArn']

def wait_for_completion(describe_function, resource_name, status_key='Status'):
    """Wait for a Forecast resource to complete"""
    max_wait_time = 3600  # 1 hour
    wait_interval = 60    # 1 minute
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        try:
            response = describe_function(resource_name)
            status = response[status_key]
            
            logger.info(f"Resource {resource_name} status: {status}")
            
            if status in ['ACTIVE', 'CREATE_FAILED']:
                return status == 'ACTIVE'
            
            time.sleep(wait_interval)
            elapsed_time += wait_interval
            
        except Exception as e:
            logger.error(f"Error checking status: {str(e)}")
            return False
    
    logger.error(f"Timeout waiting for {resource_name} to complete")
    return False

def lambda_handler(event, context):
    """Lambda handler for forecast setup"""
    try:
        logger.info("Starting forecast setup process")
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        # Create unique names for resources
        dataset_group_name = f"order-prediction-dsg-{timestamp}"
        dataset_name = f"order-prediction-ds-{timestamp}"
        predictor_name = f"order-prediction-predictor-{timestamp}"
        forecast_name = f"order-prediction-forecast-{timestamp}"
        
        # Step 1: Create dataset group
        logger.info("Creating dataset group...")
        dataset_group_arn = create_dataset_group(dataset_group_name)
        
        # Step 2: Create dataset
        logger.info("Creating dataset...")
        dataset_arn = create_dataset(dataset_name, dataset_group_arn)
        
        # Step 3: Create dataset import job (assuming data is already in S3)
        s3_path = f"s3://{processed_bucket}/forecast-ready/"
        job_name = f"order-prediction-import-{timestamp}"
        
        logger.info("Creating dataset import job...")
        import_job_arn = create_dataset_import_job(dataset_arn, s3_path, job_name)
        
        # Wait for import job to complete
        logger.info("Waiting for dataset import to complete...")
        import_success = wait_for_completion(
            lambda name: forecast_client.describe_dataset_import_job(DatasetImportJobName=name),
            job_name
        )
        
        if not import_success:
            raise Exception("Dataset import job failed")
        
        # Step 4: Create predictor
        logger.info("Creating predictor...")
        predictor_arn = create_predictor(predictor_name, dataset_group_arn)
        
        # Note: Predictor training can take hours, so we'll save the ARN and let another process handle it
        # Store the predictor ARN in SSM Parameter Store
        ssm_client.put_parameter(
            Name='/OrderPrediction/PredictorArn',
            Value=predictor_arn,
            Type='String',
            Overwrite=True
        )
        
        logger.info(f"Forecast setup initiated. Predictor ARN: {predictor_arn}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Forecast setup completed successfully',
                'predictor_arn': predictor_arn,
                'dataset_group_arn': dataset_group_arn,
                'dataset_arn': dataset_arn
            })
        }
        
    except Exception as e:
        logger.error(f"Error in forecast setup: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
