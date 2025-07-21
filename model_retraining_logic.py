"""
Enhanced Model Retraining Logic for hybrent.ipynb
This code should be added to the notebook to implement intelligent model retraining and endpoint management.
"""

import boto3
import sagemaker
from datetime import datetime, timedelta
import json
import time

def check_existing_models_and_endpoints(base_name="hybrent-deepar"):
    """
    Check for existing models and endpoints with the given base name
    Returns information about existing resources
    """
    sagemaker_client = boto3.client('sagemaker')
    
    # Get existing models
    models = []
    try:
        response = sagemaker_client.list_models(
            NameContains=base_name,
            MaxResults=50
        )
        models = response.get('Models', [])
        print(f"Found {len(models)} existing models with base name '{base_name}'")
        for model in models:
            print(f"  - {model['ModelName']} (Created: {model['CreationTime']})")
    except Exception as e:
        print(f"Error listing models: {str(e)}")
    
    # Get existing endpoints
    endpoints = []
    try:
        response = sagemaker_client.list_endpoints(
            NameContains=base_name,
            MaxResults=50
        )
        endpoints = response.get('Endpoints', [])
        print(f"Found {len(endpoints)} existing endpoints with base name '{base_name}'")
        for endpoint in endpoints:
            print(f"  - {endpoint['EndpointName']} (Status: {endpoint['EndpointStatus']}, Created: {endpoint['CreationTime']})")
    except Exception as e:
        print(f"Error listing endpoints: {str(e)}")
    
    # Get training jobs
    training_jobs = []
    try:
        response = sagemaker_client.list_training_jobs(
            NameContains=base_name,
            MaxResults=50,
            StatusEquals='Completed'
        )
        training_jobs = response.get('TrainingJobSummaries', [])
        print(f"Found {len(training_jobs)} completed training jobs with base name '{base_name}'")
        for job in training_jobs:
            print(f"  - {job['TrainingJobName']} (Status: {job['TrainingJobStatus']}, End: {job['TrainingEndTime']})")
    except Exception as e:
        print(f"Error listing training jobs: {str(e)}")
    
    return {
        'models': models,
        'endpoints': endpoints,
        'training_jobs': training_jobs
    }

def should_retrain_model(training_jobs, retrain_threshold_days=7):
    """
    Determine if we should retrain the model based on the age of the latest training job
    """
    if not training_jobs:
        print("No existing training jobs found. Will train a new model.")
        return True
    
    # Get the most recent training job
    latest_job = max(training_jobs, key=lambda x: x['TrainingEndTime'])
    latest_end_time = latest_job['TrainingEndTime']
    
    # Check if it's older than threshold
    threshold_date = datetime.now(latest_end_time.tzinfo) - timedelta(days=retrain_threshold_days)
    
    if latest_end_time < threshold_date:
        print(f"Latest model is from {latest_end_time}, which is older than {retrain_threshold_days} days. Will retrain.")
        return True
    else:
        print(f"Latest model is from {latest_end_time}, which is recent. Will use existing model.")
        return False

def cleanup_old_resources(models, endpoints, keep_latest=2):
    """
    Clean up old models and endpoints, keeping only the most recent ones
    """
    sagemaker_client = boto3.client('sagemaker')
    
    # Sort by creation time (newest first)
    models_sorted = sorted(models, key=lambda x: x['CreationTime'], reverse=True)
    endpoints_sorted = sorted(endpoints, key=lambda x: x['CreationTime'], reverse=True)
    
    # Delete old models (keep the latest N)
    models_to_delete = models_sorted[keep_latest:]
    for model in models_to_delete:
        try:
            print(f"Deleting old model: {model['ModelName']}")
            sagemaker_client.delete_model(ModelName=model['ModelName'])
        except Exception as e:
            print(f"Error deleting model {model['ModelName']}: {str(e)}")
    
    # Delete old endpoints (keep the latest N)
    endpoints_to_delete = endpoints_sorted[keep_latest:]
    for endpoint in endpoints_to_delete:
        try:
            print(f"Deleting old endpoint: {endpoint['EndpointName']}")
            sagemaker_client.delete_endpoint(EndpointName=endpoint['EndpointName'])
            # Also delete the endpoint configuration
            try:
                sagemaker_client.delete_endpoint_config(EndpointConfigName=endpoint['EndpointName'])
            except:
                pass  # Config might not exist or already deleted
        except Exception as e:
            print(f"Error deleting endpoint {endpoint['EndpointName']}: {str(e)}")

def intelligent_model_training_and_deployment(
    estimator, 
    data_channels, 
    base_name="hybrent-deepar",
    retrain_threshold_days=7,
    cleanup_old=True,
    force_retrain=False
):
    """
    Intelligent model training and deployment with the following logic:
    1. Check for existing models and endpoints
    2. Determine if retraining is needed
    3. Train new model if needed
    4. Deploy to endpoint (create new or update existing)
    5. Clean up old resources
    """
    
    print("🔍 Checking existing models and endpoints...")
    existing_resources = check_existing_models_and_endpoints(base_name)
    
    # Determine if we should retrain
    should_retrain = force_retrain or should_retrain_model(
        existing_resources['training_jobs'], 
        retrain_threshold_days
    )
    
    trained_estimator = None
    
    if should_retrain:
        print("\n🚀 Starting model training...")
        try:
            # Train the model
            estimator.fit(inputs=data_channels, wait=True)
            trained_estimator = estimator
            print("✅ Model training completed successfully!")
        except Exception as e:
            print(f"❌ Error during training: {str(e)}")
            # If training fails and we have existing models, we can still deploy the latest one
            if existing_resources['training_jobs']:
                print("Will attempt to use the latest existing model for deployment.")
                # You would need to recreate the estimator from the latest training job
                # This is more complex and depends on your specific setup
            else:
                raise e
    else:
        print("\n♻️ Using existing model (no retraining needed)")
        # If not retraining, we need to get the latest model
        # This requires recreating the estimator from the existing training job
        if existing_resources['training_jobs']:
            latest_job = max(existing_resources['training_jobs'], key=lambda x: x['TrainingEndTime'])
            print(f"Using model from training job: {latest_job['TrainingJobName']}")
            
            # Recreate estimator from existing training job
            trained_estimator = sagemaker.estimator.Estimator.attach(latest_job['TrainingJobName'])
        else:
            raise ValueError("No existing models found and retraining was skipped")
    
    # Deploy the model
    print("\n🚀 Deploying model to endpoint...")
    try:
        # Generate unique endpoint name with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        endpoint_name = f"{base_name}-{timestamp}"
        
        # Deploy the model
        predictor = trained_estimator.deploy(
            initial_instance_count=1,
            instance_type="ml.m5.large",
            endpoint_name=endpoint_name
        )
        
        print(f"✅ Model deployed to endpoint: {predictor.endpoint_name}")
        
        # Update any configuration files or environment variables with the new endpoint name
        update_endpoint_configuration(predictor.endpoint_name)
        
    except Exception as e:
        print(f"❌ Error during deployment: {str(e)}")
        raise e
    
    # Clean up old resources
    if cleanup_old:
        print("\n🧹 Cleaning up old resources...")
        # Refresh the resource list to include the newly created ones
        updated_resources = check_existing_models_and_endpoints(base_name)
        cleanup_old_resources(
            updated_resources['models'], 
            updated_resources['endpoints'], 
            keep_latest=2
        )
    
    return predictor

def update_endpoint_configuration(new_endpoint_name):
    """
    Update configuration files with the new endpoint name
    This could update Lambda environment variables, config files, etc.
    """
    print(f"📝 Updating configuration with new endpoint: {new_endpoint_name}")
    
    # Save to a configuration file
    config = {
        "endpoint_name": new_endpoint_name,
        "updated_at": datetime.now().isoformat(),
        "status": "active"
    }
    
    with open('endpoint_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("Configuration updated successfully!")
    print(f"🔗 New endpoint name: {new_endpoint_name}")
    print("💡 Remember to update your Lambda functions with this new endpoint name!")

# Example usage in the notebook:
def run_intelligent_training():
    """
    Main function to run the intelligent training and deployment process
    """
    print("🎯 Starting Intelligent Model Training and Deployment")
    print("=" * 60)
    
    # This assumes you have already set up your estimator and data_channels
    # from the previous cells in the notebook
    
    try:
        predictor = intelligent_model_training_and_deployment(
            estimator=estimator,  # From previous notebook cells
            data_channels=data_channels,  # From previous notebook cells
            base_name="hybrent-deepar",
            retrain_threshold_days=7,  # Retrain if model is older than 7 days
            cleanup_old=True,  # Clean up old resources
            force_retrain=False  # Set to True to force retraining regardless of age
        )
        
        print("\n🎉 Process completed successfully!")
        print(f"🔗 Active endpoint: {predictor.endpoint_name}")
        
        return predictor
        
    except Exception as e:
        print(f"\n❌ Process failed: {str(e)}")
        raise e

# Additional utility functions

def get_model_metrics(training_job_name):
    """
    Get training metrics for a specific training job
    """
    sagemaker_client = boto3.client('sagemaker')
    
    try:
        response = sagemaker_client.describe_training_job(TrainingJobName=training_job_name)
        
        # Extract final metrics
        final_metrics = response.get('FinalMetricDataList', [])
        
        metrics_dict = {}
        for metric in final_metrics:
            metrics_dict[metric['MetricName']] = metric['Value']
        
        return metrics_dict
    except Exception as e:
        print(f"Error getting metrics for {training_job_name}: {str(e)}")
        return {}

def compare_model_performance(training_jobs):
    """
    Compare performance metrics across different training jobs
    """
    print("📊 Comparing model performance...")
    
    performance_data = []
    for job in training_jobs:
        metrics = get_model_metrics(job['TrainingJobName'])
        performance_data.append({
            'job_name': job['TrainingJobName'],
            'end_time': job['TrainingEndTime'],
            'metrics': metrics
        })
    
    # Sort by training end time
    performance_data.sort(key=lambda x: x['end_time'], reverse=True)
    
    for data in performance_data:
        print(f"\n📈 {data['job_name']} ({data['end_time']})")
        for metric_name, value in data['metrics'].items():
            print(f"  {metric_name}: {value}")
    
    return performance_data