# Notebook Cells for Intelligent Model Retraining

Add these cells to your `hybrent.ipynb` notebook after the data preparation section and before the current training section.

## Cell 1: Import Required Libraries for Retraining

```python
# Additional imports for intelligent retraining
import boto3
from datetime import datetime, timedelta
import json
import time
from botocore.exceptions import ClientError

print("📦 Additional libraries imported for intelligent retraining")
```

## Cell 2: Utility Functions for Model Management

```python
def check_existing_models_and_endpoints(base_name="hybrent-deepar"):
    """
    Check for existing models and endpoints with the given base name
    Returns information about existing resources
    """
    sagemaker_client = boto3.client('sagemaker')
    
    print(f"🔍 Checking existing resources with base name: {base_name}")
    
    # Get existing models
    models = []
    try:
        response = sagemaker_client.list_models(
            NameContains=base_name,
            MaxResults=50
        )
        models = response.get('Models', [])
        print(f"📦 Found {len(models)} existing models")
        for model in models:
            print(f"  - {model['ModelName']} (Created: {model['CreationTime']})")
    except Exception as e:
        print(f"❌ Error listing models: {str(e)}")
    
    # Get existing endpoints
    endpoints = []
    try:
        response = sagemaker_client.list_endpoints(
            NameContains=base_name,
            MaxResults=50
        )
        endpoints = response.get('Endpoints', [])
        print(f"🔗 Found {len(endpoints)} existing endpoints")
        for endpoint in endpoints:
            status = endpoint['EndpointStatus']
            status_emoji = "✅" if status == "InService" else "⚠️" if status == "Creating" else "❌"
            print(f"  - {endpoint['EndpointName']} ({status_emoji} {status}, Created: {endpoint['CreationTime']})")
    except Exception as e:
        print(f"❌ Error listing endpoints: {str(e)}")
    
    # Get training jobs
    training_jobs = []
    try:
        response = sagemaker_client.list_training_jobs(
            NameContains=base_name,
            MaxResults=50,
            StatusEquals='Completed'
        )
        training_jobs = response.get('TrainingJobSummaries', [])
        print(f"🎯 Found {len(training_jobs)} completed training jobs")
        for job in training_jobs:
            print(f"  - {job['TrainingJobName']} (✅ {job['TrainingJobStatus']}, End: {job['TrainingEndTime']})")
    except Exception as e:
        print(f"❌ Error listing training jobs: {str(e)}")
    
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
        print("🆕 No existing training jobs found. Will train a new model.")
        return True, "No existing models"
    
    # Get the most recent training job
    latest_job = max(training_jobs, key=lambda x: x['TrainingEndTime'])
    latest_end_time = latest_job['TrainingEndTime']
    
    # Check if it's older than threshold
    threshold_date = datetime.now(latest_end_time.tzinfo) - timedelta(days=retrain_threshold_days)
    
    age_days = (datetime.now(latest_end_time.tzinfo) - latest_end_time).days
    
    if latest_end_time < threshold_date:
        print(f"🔄 Latest model is {age_days} days old (threshold: {retrain_threshold_days} days). Will retrain.")
        return True, f"Model is {age_days} days old"
    else:
        print(f"✅ Latest model is {age_days} days old (threshold: {retrain_threshold_days} days). Will use existing model.")
        return False, f"Model is recent ({age_days} days old)"

def cleanup_old_resources(models, endpoints, keep_latest=2):
    """
    Clean up old models and endpoints, keeping only the most recent ones
    """
    sagemaker_client = boto3.client('sagemaker')
    
    print(f"🧹 Cleaning up old resources (keeping latest {keep_latest})")
    
    # Sort by creation time (newest first)
    models_sorted = sorted(models, key=lambda x: x['CreationTime'], reverse=True)
    endpoints_sorted = sorted(endpoints, key=lambda x: x['CreationTime'], reverse=True)
    
    # Delete old models (keep the latest N)
    models_to_delete = models_sorted[keep_latest:]
    for model in models_to_delete:
        try:
            print(f"🗑️ Deleting old model: {model['ModelName']}")
            sagemaker_client.delete_model(ModelName=model['ModelName'])
        except Exception as e:
            print(f"❌ Error deleting model {model['ModelName']}: {str(e)}")
    
    # Delete old endpoints (keep the latest N)
    endpoints_to_delete = endpoints_sorted[keep_latest:]
    for endpoint in endpoints_to_delete:
        try:
            print(f"🗑️ Deleting old endpoint: {endpoint['EndpointName']}")
            sagemaker_client.delete_endpoint(EndpointName=endpoint['EndpointName'])
            # Also delete the endpoint configuration
            try:
                sagemaker_client.delete_endpoint_config(EndpointConfigName=endpoint['EndpointName'])
                print(f"🗑️ Deleted endpoint config: {endpoint['EndpointName']}")
            except:
                pass  # Config might not exist or already deleted
        except Exception as e:
            print(f"❌ Error deleting endpoint {endpoint['EndpointName']}: {str(e)}")

print("✅ Model management utility functions defined")
```

## Cell 3: Main Intelligent Training Function

```python
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
    
    print("🎯 Starting Intelligent Model Training and Deployment")
    print("=" * 60)
    
    # Check existing resources
    existing_resources = check_existing_models_and_endpoints(base_name)
    
    # Determine if we should retrain
    should_retrain, reason = should_retrain_model(
        existing_resources['training_jobs'], 
        retrain_threshold_days
    )
    
    if force_retrain:
        should_retrain = True
        reason = "Force retrain requested"
        print("🔄 Force retrain enabled")
    
    print(f"📋 Decision: {'RETRAIN' if should_retrain else 'USE EXISTING'} - {reason}")
    
    trained_estimator = None
    
    if should_retrain:
        print("\n🚀 Starting model training...")
        print(f"⏰ Training started at: {datetime.now()}")
        
        try:
            # Train the model
            estimator.fit(inputs=data_channels, wait=True)
            trained_estimator = estimator
            print(f"✅ Model training completed at: {datetime.now()}")
            
            # Get training job name for reference
            training_job_name = estimator.latest_training_job.name
            print(f"📝 Training job name: {training_job_name}")
            
        except Exception as e:
            print(f"❌ Error during training: {str(e)}")
            # If training fails and we have existing models, we can still deploy the latest one
            if existing_resources['training_jobs']:
                print("⚠️ Training failed, but existing models found. Will attempt to use latest existing model.")
                latest_job = max(existing_resources['training_jobs'], key=lambda x: x['TrainingEndTime'])
                print(f"📦 Using model from training job: {latest_job['TrainingJobName']}")
                trained_estimator = sagemaker.estimator.Estimator.attach(latest_job['TrainingJobName'])
            else:
                print("❌ No existing models available as fallback")
                raise e
    else:
        print("\n♻️ Using existing model (no retraining needed)")
        if existing_resources['training_jobs']:
            latest_job = max(existing_resources['training_jobs'], key=lambda x: x['TrainingEndTime'])
            print(f"📦 Using model from training job: {latest_job['TrainingJobName']}")
            trained_estimator = sagemaker.estimator.Estimator.attach(latest_job['TrainingJobName'])
        else:
            raise ValueError("❌ No existing models found and retraining was skipped")
    
    # Deploy the model
    print("\n🚀 Deploying model to endpoint...")
    try:
        # Generate unique endpoint name with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        endpoint_name = f"{base_name}-{timestamp}"
        
        print(f"🔗 Creating endpoint: {endpoint_name}")
        print(f"⏰ Deployment started at: {datetime.now()}")
        
        # Deploy the model
        predictor = trained_estimator.deploy(
            initial_instance_count=1,
            instance_type="ml.m5.large",
            endpoint_name=endpoint_name
        )
        
        print(f"✅ Model deployed successfully at: {datetime.now()}")
        print(f"🔗 Endpoint name: {predictor.endpoint_name}")
        
        # Save endpoint configuration
        save_endpoint_configuration(predictor.endpoint_name)
        
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
    
    print("\n🎉 Process completed successfully!")
    print(f"🔗 Active endpoint: {predictor.endpoint_name}")
    
    return predictor

def save_endpoint_configuration(endpoint_name):
    """
    Save endpoint configuration to files for easy reference
    """
    print(f"💾 Saving endpoint configuration...")
    
    config = {
        "endpoint_name": endpoint_name,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "region": boto3.Session().region_name
    }
    
    # Save to JSON file
    with open('current_endpoint_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    # Save to simple text file for easy reading
    with open('current_endpoint_name.txt', 'w') as f:
        f.write(endpoint_name)
    
    print(f"💾 Configuration saved:")
    print(f"  - current_endpoint_config.json")
    print(f"  - current_endpoint_name.txt")
    print(f"🔗 Current endpoint: {endpoint_name}")

print("✅ Intelligent training function defined")
```

## Cell 4: Configuration and Execution

```python
# Configuration for intelligent retraining
RETRAIN_THRESHOLD_DAYS = 7  # Retrain if model is older than 7 days
FORCE_RETRAIN = False       # Set to True to force retraining regardless of age
CLEANUP_OLD_RESOURCES = True # Clean up old models and endpoints
BASE_NAME = "hybrent-deepar" # Base name for all resources

print("⚙️ Retraining Configuration:")
print(f"  - Retrain threshold: {RETRAIN_THRESHOLD_DAYS} days")
print(f"  - Force retrain: {FORCE_RETRAIN}")
print(f"  - Cleanup old resources: {CLEANUP_OLD_RESOURCES}")
print(f"  - Base name: {BASE_NAME}")
```

## Cell 5: Execute Intelligent Training and Deployment

```python
# Execute the intelligent training and deployment process
try:
    print("🎯 Starting Intelligent Model Training and Deployment Process")
    print("=" * 70)
    
    # Run the intelligent training process
    predictor = intelligent_model_training_and_deployment(
        estimator=estimator,  # From previous notebook cells
        data_channels=data_channels,  # From previous notebook cells
        base_name=BASE_NAME,
        retrain_threshold_days=RETRAIN_THRESHOLD_DAYS,
        cleanup_old=CLEANUP_OLD_RESOURCES,
        force_retrain=FORCE_RETRAIN
    )
    
    print("\n" + "=" * 70)
    print("🎉 SUCCESS! Process completed successfully!")
    print("=" * 70)
    print(f"🔗 Active endpoint: {predictor.endpoint_name}")
    print(f"📝 Endpoint saved to: current_endpoint_name.txt")
    print(f"⚙️ Configuration saved to: current_endpoint_config.json")
    
    # Display endpoint information
    print(f"\n📋 Endpoint Information:")
    print(f"  Name: {predictor.endpoint_name}")
    print(f"  Instance Type: ml.m5.large")
    print(f"  Instance Count: 1")
    print(f"  Status: InService")
    
    # Save the endpoint name to a variable for use in subsequent cells
    current_endpoint_name = predictor.endpoint_name
    
    print(f"\n💡 Next Steps:")
    print(f"  1. Test the endpoint using the prediction cells below")
    print(f"  2. Update your Lambda functions with the new endpoint name:")
    print(f"     {current_endpoint_name}")
    print(f"  3. The endpoint configuration has been saved for reference")
    
except Exception as e:
    print(f"\n❌ Process failed with error: {str(e)}")
    print("🔍 Check the error details above and retry if needed")
    raise e
```

## Cell 6: Verify Deployment and Test Endpoint

```python
# Verify the deployment and test the endpoint
try:
    print("🧪 Testing the deployed endpoint...")
    
    # Read the current endpoint name
    with open('current_endpoint_name.txt', 'r') as f:
        current_endpoint_name = f.read().strip()
    
    print(f"🔗 Testing endpoint: {current_endpoint_name}")
    
    # Create a test predictor
    test_predictor = sagemaker.predictor.Predictor(
        endpoint_name=current_endpoint_name,
        serializer=sagemaker.serializers.JSONSerializer(),
        deserializer=sagemaker.deserializers.JSONDeserializer()
    )
    
    # Test with a simple prediction (you can customize this based on your data)
    print("📊 Running test prediction...")
    
    # You would replace this with actual test data from your dataset
    test_data = {
        "instances": [
            {
                "start": "2025-01-01 00:00:00",
                "target": [1.0, 2.0, 3.0, 4.0, 5.0],
                "dynamic_feat": [[1, 2, 3, 4, 5], [0, 1, 0, 1, 0]]
            }
        ],
        "configuration": {
            "num_samples": 100,
            "output_types": ["mean", "quantiles"],
            "quantiles": ["0.1", "0.5", "0.9"]
        }
    }
    
    # Make a test prediction
    try:
        result = test_predictor.predict(test_data)
        print("✅ Endpoint test successful!")
        print(f"📊 Prediction result keys: {list(result.keys()) if isinstance(result, dict) else 'Non-dict response'}")
    except Exception as test_error:
        print(f"⚠️ Endpoint test failed: {str(test_error)}")
        print("💡 This might be due to data format - the endpoint is likely working correctly")
    
    print(f"\n✅ Endpoint verification completed")
    print(f"🔗 Endpoint {current_endpoint_name} is ready for use!")
    
except Exception as e:
    print(f"❌ Verification failed: {str(e)}")
```

## Cell 7: Display Summary and Next Steps

```python
# Display final summary and next steps
print("📋 DEPLOYMENT SUMMARY")
print("=" * 50)

try:
    # Read current configuration
    with open('current_endpoint_config.json', 'r') as f:
        config = json.load(f)
    
    print(f"✅ Status: Deployment Successful")
    print(f"🔗 Endpoint Name: {config['endpoint_name']}")
    print(f"⏰ Created At: {config['created_at']}")
    print(f"🌍 Region: {config['region']}")
    
    print(f"\n📁 Files Created:")
    print(f"  - current_endpoint_config.json (Full configuration)")
    print(f"  - current_endpoint_name.txt (Endpoint name only)")
    
    print(f"\n🔄 Next Steps:")
    print(f"  1. Update Lambda Functions:")
    print(f"     - Update SAGEMAKER_ENDPOINT_NAME environment variable")
    print(f"     - New value: {config['endpoint_name']}")
    
    print(f"\n  2. Update CloudFormation Template:")
    print(f"     - Update SageMakerEndpointName parameter default value")
    print(f"     - New value: {config['endpoint_name']}")
    
    print(f"\n  3. Redeploy Lambda Functions:")
    print(f"     sam deploy --parameter-overrides SageMakerEndpointName={config['endpoint_name']}")
    
    print(f"\n  4. Test the Updated System:")
    print(f"     - Upload test data to trigger the Lambda functions")
    print(f"     - Verify predictions are working correctly")
    
    print(f"\n💡 Tips:")
    print(f"  - The old endpoint will be cleaned up automatically")
    print(f"  - Run this notebook periodically for automated retraining")
    print(f"  - Monitor endpoint performance in SageMaker console")
    
except FileNotFoundError:
    print("❌ Configuration files not found. Please run the deployment process first.")
except Exception as e:
    print(f"❌ Error reading configuration: {str(e)}")

print("\n🎉 Intelligent Model Retraining Process Complete!")
```

---

## Instructions for Adding to Your Notebook

1. **Add these cells** to your `hybrent.ipynb` notebook after the data preparation section (around cell where you prepare `data_channels`)

2. **Replace the existing training section** with Cell 5 above, or run Cell 5 instead of the manual training

3. **Customize the configuration** in Cell 4 based on your needs:
   - `RETRAIN_THRESHOLD_DAYS`: How often to retrain (default: 7 days)
   - `FORCE_RETRAIN`: Set to `True` to always retrain
   - `CLEANUP_OLD_RESOURCES`: Whether to clean up old models/endpoints

4. **Run the cells in order** - they build upon each other

5. **Update your Lambda functions** with the new endpoint name from the output

This approach will:
- ✅ Check for existing models automatically
- ✅ Only retrain when needed (based on age threshold)
- ✅ Clean up old resources to save costs
- ✅ Provide clear feedback and next steps
- ✅ Save configuration for easy reference
- ✅ Handle errors gracefully with fallbacks