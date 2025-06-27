# 🔧 Troubleshooting Guide

## 🚨 Common Deployment Issues

### Issue 1: "Unrecognized resource types: [AWS::S3::BucketNotification]"

**Error Message:**
```
Template format error: Unrecognized resource types: [AWS::S3::BucketNotification]
```

**Root Cause:** 
The CloudFormation template was using an invalid resource type for S3 notifications.

**Solution:**
✅ **FIXED** - The updated template removes the problematic S3 event configurations and uses a simpler approach.

### Issue 2: "Layer sizes too big"

**Error Message:**
```
Layer size exceeds maximum allowed size
```

**Root Cause:** 
The AWS Lambda layer for pandas/numpy is too large when combined with our function code.

**Solution:**
✅ **FIXED** - Removed the pandas layer and included pandas directly in requirements.txt with smaller memory allocation.

### Issue 3: S3 Bucket Creation Issues

**Error Message:**
```
S3 Bucket not specified, use --s3-bucket to specify a bucket name
```

**Solution:**
```bash
sam deploy --guided --resolve-s3
```

### Issue 4: Multiple Resources Fail to Create

**Error Message:**
```
The following resource(s) failed to create: [LambdaExecutionRole, ForecastRole, ModelArtifactsBucket, FeedbackTable, 
ProductLookupTable, ProcessedDataBucket, ResultsBucket, PredictionCacheTable, OrderPredictionApiDeploymentcc0d2c4d8a, 
RawDataBucket]. Rollback requested by user.
```

**Root Cause:** 
This error typically occurs due to one of several issues:
1. Insufficient IAM permissions for creating IAM roles or S3 buckets
2. Resource name conflicts (S3 buckets with the same name already exist)
3. Service quotas being exceeded
4. Region restrictions for certain services

**Solution:**

Try the following troubleshooting steps:

```bash
# 1. Check your IAM permissions
aws iam get-user
aws iam list-attached-user-policies --user-name YOUR_USERNAME

# 2. Check for existing S3 buckets with conflicting names
aws s3 ls | grep "order-prediction"

# 3. Try deployment with a unique stack name
./deploy.sh --stack-name order-prediction-unique-$(date +%s)

# 4. Check if all required services are available in your region
aws service-quotas list-aws-default-service-quotas --service-code lambda
aws service-quotas list-aws-default-service-quotas --service-code dynamodb
```

If the issue persists, try the Clean Deployment approach in the "Quick Fix Deployment" section below.

## 🚀 Quick Fix Deployment

If you're still having issues, use this simplified deployment approach:

### Step 1: Clean Deployment
```bash
# If you have a failed stack, delete it first
aws cloudformation delete-stack --stack-name order-prediction-enhanced --region us-east-2

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete --stack-name order-prediction-enhanced --region us-east-2
```

### Step 2: Fresh Deployment
```bash
cd procurement_partners_deployment_package
sam build
sam deploy --guided --resolve-s3
```

### Step 3: Configuration Prompts
When prompted, use these values:
- **Stack Name**: `order-prediction-enhanced`
- **AWS Region**: `us-east-2` (or your preferred region)
- **Parameter Environment**: `dev`
- **Parameter BedrockModelId**: `anthropic.claude-3-7-sonnet-20250219-v1:0`
- **Parameter EnableProductLevelForecasting**: `true`
- **Confirm changes before deploy**: `Y`
- **Allow SAM CLI to create IAM roles**: `Y`
- **Save parameters to samconfig.toml**: `Y`

## 🔍 Verification Steps

After deployment, verify everything is working:

### 1. Check Stack Status
```bash
aws cloudformation describe-stacks --stack-name order-prediction-enhanced --region us-east-2 --query 'Stacks[0].StackStatus'
```
Should return: `"CREATE_COMPLETE"`

### 2. Check Lambda Functions
```bash
aws lambda list-functions --region us-east-2 --query 'Functions[?contains(FunctionName, `order-prediction-enhanced`)].FunctionName'
```

### 3. Check API Gateway
```bash
aws apigateway get-rest-apis --region us-east-2 --query 'items[?contains(name, `order-prediction`)].{Name:name,Id:id}'
```

### 4. Test API Endpoint
```bash
# Get the API endpoint from stack outputs
API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name order-prediction-enhanced --region us-east-2 --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)

# Test the endpoint
curl "$API_ENDPOINT/predict?customerId=TEST&facilityId=TEST"
```

## 🐛 Still Having Issues?

### Check CloudFormation Events
```bash
aws cloudformation describe-stack-events --stack-name order-prediction-enhanced --region us-east-2 --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'
```

### Check Lambda Logs
```bash
sam logs --stack-name order-prediction-enhanced --region us-east-2
```

### Manual S3 Event Setup (If Needed)
If S3 events aren't working, you can set them up manually:

1. Go to S3 Console
2. Select your raw data bucket
3. Go to Properties → Event notifications
4. Create notification:
   - Event types: `All object create events`
   - Suffix: `.csv`
   - Destination: Lambda function (select your feature engineering function)

## 📞 Getting Help

### AWS Support Resources
- **CloudFormation Console**: Check stack events and resources
- **CloudWatch Logs**: Detailed error messages
- **AWS CLI**: Use `--debug` flag for verbose output

### Debug Commands
```bash
# Verbose SAM deployment
sam deploy --debug

# Check AWS credentials
aws sts get-caller-identity

# Check region configuration
aws configure get region

# List all stacks
aws cloudformation list-stacks --region us-east-2
```

## ✅ Success Indicators

Your deployment is successful when:
- ✅ CloudFormation stack status is `CREATE_COMPLETE`
- ✅ All 8 Lambda functions are created
- ✅ API Gateway returns responses (even errors are OK initially)
- ✅ S3 buckets are created and accessible
- ✅ DynamoDB tables are created

## 🎯 Next Steps After Successful Deployment

1. **Upload Sample Data**:
   ```bash
   echo "CreateDate,CustomerID,FacilityID,ProductID,Quantity
   2024-01-01,CUST001,FAC001,PROD001,100" > sample.csv
   
   aws s3 cp sample.csv s3://order-prediction-raw-data-{ACCOUNT-ID}-dev/
   ```

2. **Monitor Processing**:
   ```bash
   sam logs --stack-name order-prediction-enhanced --tail
   ```

3. **Test APIs**:
   ```bash
   curl "$API_ENDPOINT/predict?customerId=CUST001&facilityId=FAC001"
   ```

---

**Remember**: The initial deployment creates the infrastructure. Data processing and predictions require actual data to be uploaded to S3.
