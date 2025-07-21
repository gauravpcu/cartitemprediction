# Lambda Optimization Troubleshooting Guide

## 🚨 Common Issues and Solutions

This guide provides comprehensive troubleshooting for the optimized Lambda deployment process, covering layer management, size validation, and deployment issues.

## 📋 Quick Diagnosis

### Check System Status
```bash
# Quick health check
./scripts/manage-layers.sh status

# Validate current state
python3 scripts/size-validation.py check --verbose

# Check AWS connectivity
aws sts get-caller-identity
```

## 🔧 Build Process Issues

### Issue 1: Layer Build Failures

#### Symptom
```
[ERROR] Failed to install dependencies for core-data-science
pip install failed with exit code 1
```

#### Root Causes
- Missing system dependencies
- Python version incompatibility
- Network connectivity issues
- Insufficient disk space

#### Solutions

**1. Check Prerequisites**
```bash
# Verify Python version
python3 --version  # Should be 3.9+

# Check pip version
pip3 --version

# Verify disk space
df -h .
```

**2. Clean and Retry**
```bash
# Clean all build artifacts
./build.sh --clean

# Rebuild with verbose output
./build.sh --layers-only --verbose
```

**3. Manual Layer Build**
```bash
# Build specific layer manually
cd layers/core-data-science
pip3 install -r requirements.txt -t python/ --upgrade
```

**4. Platform-Specific Issues**
```bash
# For macOS with M1/M2 chips
pip3 install -r requirements.txt -t python/ \
  --platform manylinux2014_x86_64 \
  --only-binary=:all: \
  --upgrade

# For Linux compatibility
docker run --rm -v $(pwd):/workspace \
  python:3.9-slim \
  pip install -r /workspace/requirements.txt -t /workspace/python/
```

### Issue 2: Size Validation Failures

#### Symptom
```
[ERROR] Layer 'ml-libraries' exceeds size limit: 125MB > 105MB
Size validation failed. Deployment aborted.
```

#### Solutions

**1. Run Advanced Optimization**
```bash
# Optimize specific layer
python3 scripts/layer-utils.py optimize --layer ml-libraries --verbose

# Check what's taking space
python3 scripts/size-validation.py report --format text | grep -A 10 "ml-libraries"
```

**2. Manual Size Reduction**
```bash
# Remove large unnecessary files
cd layers/ml-libraries/python

# Remove test data and examples
find . -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "examples" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.so" -size +10M -delete

# For scikit-learn specifically
rm -rf sklearn/datasets/
rm -rf sklearn/experimental/
```

**3. Selective Package Installation**
```bash
# Install only essential scikit-learn modules
pip3 install --no-deps scikit-learn -t python/
pip3 install joblib -t python/

# Manually copy only needed sklearn modules
mkdir -p python/sklearn
cp -r /usr/local/lib/python3.9/site-packages/sklearn/{ensemble,linear_model,preprocessing,metrics} python/sklearn/
```

### Issue 3: Import Validation Failures

#### Symptom
```
[ERROR] Import validation failed for layer: core-data-science
✗ Failed to import pandas: No module named 'numpy'
```

#### Solutions

**1. Check Layer Dependencies**
```bash
# Validate layer structure
ls -la layers/core-data-science/python/

# Test imports manually
python3 -c "
import sys
sys.path.insert(0, 'layers/core-data-science/python')
import pandas
print('Pandas version:', pandas.__version__)
"
```

**2. Fix Missing Dependencies**
```bash
# Reinstall with all dependencies
cd layers/core-data-science
rm -rf python/
pip3 install -r requirements.txt -t python/ --upgrade
```

**3. Layer Dependency Order**
```bash
# Ensure layers are built in correct order
./build.sh --clean
# Build order: core-data-science → ml-libraries → aws-utilities
```

## 🚀 Deployment Issues

### Issue 4: SAM Build Failures

#### Symptom
```
Build Failed
Error: PythonPipBuilder:ResolveDependencies - {pandas==2.0.3(wheel)}
```

#### Solutions

**1. Clear SAM Cache**
```bash
# Remove SAM build cache
rm -rf .aws-sam/

# Rebuild
sam build --use-container
```

**2. Use Container Build**
```bash
# Build in container for consistency
sam build --use-container --container-env-var-file env.json
```

**3. Fix Requirements Conflicts**
```bash
# Check for conflicting requirements
cd functions/enhanced_feature_engineering
pip-compile requirements.txt --verbose

# Remove layer dependencies from function requirements
# Keep only function-specific dependencies
```

### Issue 5: CloudFormation Stack Failures

#### Symptom
```
CREATE_FAILED: The following resource(s) failed to create: 
[CoreDataScienceLayer, MLLibrariesLayer]
```

#### Solutions

**1. Check Layer Size Limits**
```bash
# Validate before deployment
python3 scripts/size-validation.py check

# If layers are too large, optimize them
./scripts/manage-layers.sh optimize all
```

**2. Check AWS Service Limits**
```bash
# Check Lambda service quotas
aws service-quotas get-service-quota \
  --service-code lambda \
  --quota-code L-B99A9384  # Layer storage quota

# List current layers
aws lambda list-layers --region us-east-1
```

**3. Incremental Deployment**
```bash
# Deploy layers first
sam deploy --parameter-overrides DeployFunctionsOnly=false

# Then deploy functions
sam deploy --parameter-overrides DeployLayersOnly=false
```

### Issue 6: Function Runtime Errors

#### Symptom
```
[ERROR] Runtime.ImportModuleError: Unable to import module 'app': 
No module named 'pandas'
```

#### Solutions

**1. Verify Layer Configuration**
```bash
# Check SAM template layer references
grep -A 5 "Layers:" template.yaml

# Ensure function references correct layers
```

**2. Test Layer Imports Locally**
```bash
# Simulate Lambda environment
export PYTHONPATH="layers/core-data-science/python:layers/ml-libraries/python:$PYTHONPATH"
python3 functions/enhanced_feature_engineering/app.py
```

**3. Check Layer ARNs**
```bash
# Get deployed layer ARNs
aws lambda list-layer-versions --layer-name core-data-science-layer

# Update function configuration if needed
aws lambda update-function-configuration \
  --function-name YourFunction \
  --layers arn:aws:lambda:region:account:layer:core-data-science-layer:1
```

## 🔍 Performance Issues

### Issue 7: Slow Cold Starts

#### Symptom
- Cold start times > 5 seconds
- Timeout errors during initialization

#### Solutions

**1. Optimize Layer Loading**
```python
# In Lambda function code
import sys
import os

# Optimize import order
sys.path.insert(0, '/opt/python')  # Layer path

# Lazy imports
def get_pandas():
    global pd
    if 'pd' not in globals():
        import pandas as pd
    return pd
```

**2. Reduce Layer Size Further**
```bash
# Ultra-aggressive optimization
python3 scripts/layer-utils.py optimize --layer core-data-science --verbose

# Remove unused modules
cd layers/core-data-science/python
rm -rf pandas/tests/
rm -rf numpy/tests/
find . -name "*.pyc" -delete
```

**3. Use Provisioned Concurrency**
```yaml
# In template.yaml
ProvisionedConcurrencyConfig:
  ProvisionedConcurrencyUnits: 2
```

### Issue 8: Memory Issues

#### Symptom
```
[ERROR] Runtime exited with error: signal: killed
Runtime.ExitError
```

#### Solutions

**1. Increase Memory Allocation**
```yaml
# In template.yaml
MemorySize: 2048  # Increase from 1024
```

**2. Optimize Memory Usage**
```python
# In function code
import gc

def lambda_handler(event, context):
    try:
        # Your code here
        result = process_data()
        return result
    finally:
        # Force garbage collection
        gc.collect()
```

**3. Monitor Memory Usage**
```python
import psutil
import os

def log_memory_usage():
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    print(f"Memory usage: {memory_mb:.2f} MB")
```

## 🛠️ Advanced Troubleshooting

### Debug Layer Contents

```bash
# Inspect layer structure
find layers/core-data-science/python -type f -name "*.py" | head -20

# Check package versions
python3 -c "
import sys
sys.path.insert(0, 'layers/core-data-science/python')
import pandas, numpy
print(f'Pandas: {pandas.__version__}')
print(f'NumPy: {numpy.__version__}')
"

# Analyze layer size breakdown
du -sh layers/*/python/* | sort -hr
```

### Test Layer Compatibility

```bash
# Create test script
cat > test_layer.py << 'EOF'
import sys
import os

# Add layer paths
sys.path.insert(0, 'layers/core-data-science/python')
sys.path.insert(0, 'layers/ml-libraries/python')
sys.path.insert(0, 'layers/aws-utilities/python')

try:
    import pandas as pd
    import numpy as np
    import sklearn
    import boto3
    
    print("✅ All imports successful")
    print(f"Pandas: {pd.__version__}")
    print(f"NumPy: {np.__version__}")
    print(f"Scikit-learn: {sklearn.__version__}")
    print(f"Boto3: {boto3.__version__}")
    
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)
EOF

python3 test_layer.py
```

### Monitor Build Process

```bash
# Enable detailed logging
export SAM_CLI_DEBUG=1
export AWS_SAM_CLI_TELEMETRY=0

# Build with maximum verbosity
./build.sh --verbose 2>&1 | tee build.log

# Analyze build log
grep -i error build.log
grep -i warning build.log
```

## 📊 Monitoring and Alerting

### Set Up Monitoring

```bash
# Create monitoring script
cat > monitor_optimization.py << 'EOF'
import boto3
import json
from datetime import datetime

def check_function_sizes():
    lambda_client = boto3.client('lambda')
    
    functions = lambda_client.list_functions()
    
    for func in functions['Functions']:
        if 'item-prediction' in func['FunctionName']:
            size_mb = func['CodeSize'] / (1024 * 1024)
            print(f"{func['FunctionName']}: {size_mb:.2f}MB")
            
            if size_mb > 50:  # Alert threshold
                print(f"⚠️  WARNING: {func['FunctionName']} is large!")

if __name__ == "__main__":
    check_function_sizes()
EOF

python3 monitor_optimization.py
```

### CloudWatch Alarms

```yaml
# Add to template.yaml
LargeFunctionAlarm:
  Type: AWS::CloudWatch::Alarm
  Properties:
    AlarmName: Lambda-Function-Size-Alert
    AlarmDescription: Alert when function size is large
    MetricName: CodeSize
    Namespace: AWS/Lambda
    Statistic: Maximum
    Period: 300
    EvaluationPeriods: 1
    Threshold: 52428800  # 50MB in bytes
    ComparisonOperator: GreaterThanThreshold
```

## 🔄 Recovery Procedures

### Complete Rollback

```bash
# If deployment completely fails
sam delete --stack-name item-prediction --region us-east-1

# Clean everything
rm -rf .aws-sam/
rm -rf layers/*/python/

# Start fresh
./build.sh --clean
./deploy.sh
```

### Partial Recovery

```bash
# Rollback to previous layer version
aws lambda update-function-configuration \
  --function-name item-prediction-DataValidation \
  --layers arn:aws:lambda:us-east-1:123456789:layer:core-data-science-layer:1

# Or update specific layer
sam deploy --parameter-overrides UpdateLayersOnly=true
```

### Emergency Fixes

```bash
# Quick fix for oversized layer
cd layers/ml-libraries/python
rm -rf sklearn/datasets/
zip -r ../ml-libraries-fixed.zip .

# Update layer directly
aws lambda publish-layer-version \
  --layer-name ml-libraries-layer \
  --zip-file fileb://../ml-libraries-fixed.zip \
  --compatible-runtimes python3.9
```

## 📞 Getting Help

### Diagnostic Information to Collect

```bash
# System information
echo "=== System Info ==="
uname -a
python3 --version
pip3 --version
sam --version
aws --version

echo "=== Layer Status ==="
./scripts/manage-layers.sh status

echo "=== Size Report ==="
python3 scripts/size-validation.py report --format text

echo "=== Build Log ==="
tail -50 build.log

echo "=== AWS Info ==="
aws sts get-caller-identity
aws configure list
```

### Support Channels

1. **AWS Support**: For service-specific issues
2. **CloudWatch Logs**: Detailed error information
3. **GitHub Issues**: For template and script issues
4. **AWS Forums**: Community support

### Escalation Process

1. **Level 1**: Check this troubleshooting guide
2. **Level 2**: Run diagnostic scripts and collect logs
3. **Level 3**: Contact AWS Support with diagnostic information
4. **Level 4**: Engage AWS Solutions Architect

---

**💡 Pro Tip**: Always test changes in a development environment before applying to production. Keep backups of working configurations and use version control for all changes.

For additional support, refer to the main optimization guide or contact your AWS solutions architect.