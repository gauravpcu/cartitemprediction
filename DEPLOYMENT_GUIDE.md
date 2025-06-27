# Enhanced Order Prediction Solution - Deployment Guide

This guide provides step-by-step instructions for deploying the Enhanced Order Prediction Solution with product-level forecasting capabilities.

## 🎯 Overview

This deployment package includes:
- **Complete CloudFormation Template**: Ready-to-deploy infrastructure
- **Enhanced Lambda Functions**: All 8 Lambda functions with proper code
- **Automated Deployment Script**: One-command deployment
- **Comprehensive Documentation**: Complete setup and usage guides

## 📋 Pre-Deployment Checklist

### 1. AWS Account Setup
- [ ] AWS account with appropriate permissions
- [ ] AWS CLI installed and configured
- [ ] SAM CLI installed (version 1.50.0 or higher)
- [ ] Valid AWS credentials configured

### 2. Service Availability Check
Ensure these services are available in your target region:
- [ ] Amazon Forecast
- [ ] Amazon Bedrock (with Claude model access)
- [ ] AWS Lambda
- [ ] Amazon API Gateway
- [ ] Amazon DynamoDB
- [ ] Amazon S3

### 3. Required Tools
- [ ] `jq` (for JSON parsing)
- [ ] `curl` (for API testing)
- [ ] `unzip` (for package extraction)

## 🚀 Deployment Steps

### Step 1: Extract and Prepare

```bash
# Extract the deployment package
unzip procurement_partners_deployment_package.zip
cd procurement_partners_deployment_package

# Verify package contents
ls -la
```

Expected contents:
```
├── template.yaml                 # CloudFormation template
├── deploy.sh                     # Deployment script
├── README.md                     # Main documentation
├── DEPLOYMENT_GUIDE.md          # This file
└── functions/                   # Lambda functions
    ├── enhanced_feature_engineering/
    ├── enhanced_predictions/
    ├── data_validation/
    ├── forecast_setup/
    ├── prediction_api/
    ├── product_prediction_api/
    ├── recommend_api/
    └── feedback_api/
```

### Step 2: Configure Deployment

#### Option A: Default Deployment (Recommended for Testing)
```bash
./deploy.sh
```

#### Option B: Custom Configuration
```bash
./deploy.sh \
  --stack-name my-order-prediction \
  --region us-east-1 \
  --environment prod \
  --bedrock-model anthropic.claude-3-7-sonnet-20250219-v1:0
```

#### Available Configuration Options:
- `--stack-name`: CloudFormation stack name (default: order-prediction-enhanced)
- `--region`: AWS region (default: us-east-2)
- `--environment`: Environment tag (dev/test/prod, default: dev)
- `--bedrock-model`: Bedrock model ID (default: anthropic.claude-3-7-sonnet-20250219-v1:0)
- `--disable-product-forecasting`: Disable product-level features

### Step 3: Monitor Deployment

The deployment script will:
1. ✅ Check prerequisites
2. 🔨 Build SAM application
3. 🚀 Deploy CloudFormation stack
4. 📊 Display deployment outputs

Expected deployment time: **5-10 minutes**

### Step 4: Verify Deployment

After successful deployment, you'll see outputs like:
```
🎉 Deployment completed successfully!
==================================================
📋 Important Information:

API Endpoints:
  Main API: https://abc123.execute-api.us-east-2.amazonaws.com/Prod/
  Product Predictions: https://abc123.execute-api.us-east-2.amazonaws.com/Prod/predict/products

S3 Buckets:
  Raw Data: order-prediction-raw-data-123456789-dev
  Processed Data: order-prediction-processed-data-123456789-dev
```

## 📊 Post-Deployment Setup

### Step 1: Prepare Sample Data

Create a sample CSV file with your historical order data:

```csv
CreateDate,CustomerID,FacilityID,ProductID,Quantity,UnitPrice,ProductCategory,ProductDescription
2024-01-01,CUST001,FAC001,PROD001,100,25.50,Electronics,Widget A
2024-01-02,CUST001,FAC001,PROD002,50,15.75,Office Supplies,Paper Clips
2024-01-03,CUST002,FAC002,PROD001,75,25.50,Electronics,Widget A
```

### Step 2: Upload Data

```bash
# Replace with your actual bucket name from deployment output
RAW_BUCKET="order-prediction-raw-data-123456789-dev"

# Upload your data
aws s3 cp sample-orders.csv s3://$RAW_BUCKET/
```

### Step 3: Monitor Processing

```bash
# Check processing logs
sam logs --stack-name order-prediction-enhanced --region us-east-2 --tail

# Check S3 for processed data
aws s3 ls s3://order-prediction-processed-data-123456789-dev/processed/
```

### Step 4: Test APIs

```bash
# Replace with your actual API endpoint
API_ENDPOINT="https://abc123.execute-api.us-east-2.amazonaws.com/Prod"

# Test basic prediction
curl "$API_ENDPOINT/predict?customerId=CUST001&facilityId=FAC001"

# Test product-level prediction
curl "$API_ENDPOINT/predict/products?customerId=CUST001&facilityId=FAC001"

# Test recommendations
curl "$API_ENDPOINT/recommend?customerId=CUST001&facilityId=FAC001&type=reorder"
```

## 🔧 Configuration Options

### Environment Variables

The solution can be customized through CloudFormation parameters:

| Parameter | Description | Default | Options |
|-----------|-------------|---------|---------|
| Environment | Deployment environment | dev | dev, test, prod |
| BedrockModelId | Bedrock model for AI insights | anthropic.claude-3-7-sonnet-20250219-v1:0 | Any available Bedrock model |
| EnableProductLevelForecasting | Enable product-level features | true | true, false |

### Updating Configuration

To update configuration after deployment:

```bash
# Update with new parameters
sam deploy \
  --stack-name order-prediction-enhanced \
  --parameter-overrides \
    Environment=prod \
    BedrockModelId=anthropic.claude-3-sonnet \
  --confirm-changeset
```

## 🔍 Troubleshooting

### Common Deployment Issues

#### 1. SAM Build Failures
```bash
# Error: SAM build failed
# Solution: Check Python version and dependencies
python --version  # Should be 3.9+
pip install --upgrade aws-sam-cli
```

#### 2. CloudFormation Stack Failures
```bash
# Check stack events for specific errors
aws cloudformation describe-stack-events \
  --stack-name order-prediction-enhanced \
  --region us-east-2
```

#### 3. Permission Issues
```bash
# Verify AWS credentials and permissions
aws sts get-caller-identity
aws iam get-user
```

#### 4. Service Availability
```bash
# Check if Bedrock is available in your region
aws bedrock list-foundation-models --region us-east-2

# Check if Forecast is available
aws forecast list-datasets --region us-east-2
```

### Data Processing Issues

#### 1. Feature Engineering Failures
- **Symptom**: No processed data in S3
- **Solution**: Check data format and column names
- **Debug**: View Lambda logs for specific errors

#### 2. Forecast Creation Issues
- **Symptom**: Predictions return errors
- **Solution**: Ensure minimum 100 data points per time series
- **Debug**: Check Forecast console for predictor status

#### 3. API Response Issues
- **Symptom**: API returns 500 errors
- **Solution**: Check Lambda function logs
- **Debug**: Test individual Lambda functions

### Performance Issues

#### 1. Slow API Responses
- **Solution**: Enable API Gateway caching
- **Solution**: Increase Lambda memory allocation
- **Solution**: Optimize DynamoDB read/write capacity

#### 2. High Costs
- **Solution**: Implement S3 lifecycle policies
- **Solution**: Use DynamoDB on-demand billing
- **Solution**: Delete unused Forecast resources

## 📈 Scaling Considerations

### For Production Deployment

1. **Multi-Region Setup**
   ```bash
   # Deploy to multiple regions
   ./deploy.sh --region us-east-1 --environment prod
   ./deploy.sh --region eu-west-1 --environment prod
   ```

2. **Enhanced Monitoring**
   - Enable AWS X-Ray tracing
   - Set up CloudWatch dashboards
   - Configure SNS notifications for alarms

3. **Security Hardening**
   - Deploy in VPC
   - Enable API Gateway authentication
   - Implement WAF rules

4. **Data Management**
   - Implement data archiving
   - Set up cross-region replication
   - Enable point-in-time recovery for DynamoDB

### Performance Optimization

1. **Lambda Optimization**
   ```yaml
   # In template.yaml, adjust memory and timeout
   MemorySize: 2048  # Increase for large datasets
   Timeout: 300      # Increase for complex processing
   ```

2. **DynamoDB Optimization**
   ```yaml
   # Use provisioned capacity for predictable workloads
   BillingMode: PROVISIONED
   ProvisionedThroughput:
     ReadCapacityUnits: 100
     WriteCapacityUnits: 100
   ```

3. **API Gateway Optimization**
   ```yaml
   # Enable caching
   CacheClusterEnabled: true
   CacheClusterSize: '0.5'
   CacheTtlInSeconds: 300
   ```

## 🔄 Maintenance and Updates

### Regular Maintenance Tasks

1. **Weekly**
   - Review CloudWatch logs for errors
   - Check API performance metrics
   - Monitor costs and usage

2. **Monthly**
   - Update Lambda function code if needed
   - Review and optimize DynamoDB usage
   - Clean up old Forecast resources

3. **Quarterly**
   - Review and update security settings
   - Optimize costs based on usage patterns
   - Update documentation

### Updating the Solution

```bash
# Update Lambda function code
sam build
sam deploy --stack-name order-prediction-enhanced

# Update specific function
aws lambda update-function-code \
  --function-name order-prediction-enhanced-EnhancedPredictionsFunction \
  --zip-file fileb://new-function.zip
```

## 🆘 Support and Resources

### Getting Help

1. **AWS Documentation**
   - [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
   - [Amazon Forecast Documentation](https://docs.aws.amazon.com/forecast/)
   - [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)

2. **Troubleshooting Resources**
   - CloudWatch Logs: Detailed error information
   - AWS Support: For service-specific issues
   - AWS Forums: Community support

3. **Monitoring Tools**
   - CloudWatch Dashboards
   - AWS X-Ray (if enabled)
   - AWS Cost Explorer

### Emergency Procedures

#### Complete Rollback
```bash
# Delete the entire stack
sam delete --stack-name order-prediction-enhanced --region us-east-2
```

#### Partial Rollback
```bash
# Rollback to previous version
aws cloudformation cancel-update-stack \
  --stack-name order-prediction-enhanced
```

## ✅ Deployment Checklist

### Pre-Deployment
- [ ] AWS CLI configured
- [ ] SAM CLI installed
- [ ] Required permissions verified
- [ ] Target region supports all services
- [ ] Sample data prepared

### During Deployment
- [ ] Deployment script runs without errors
- [ ] CloudFormation stack creates successfully
- [ ] All Lambda functions deploy correctly
- [ ] API Gateway endpoints are accessible

### Post-Deployment
- [ ] Sample data uploaded to S3
- [ ] Data processing completes successfully
- [ ] API endpoints return valid responses
- [ ] CloudWatch logs show no errors
- [ ] Monitoring and alarms configured

### Production Readiness
- [ ] Security review completed
- [ ] Performance testing done
- [ ] Backup and recovery procedures tested
- [ ] Documentation updated
- [ ] Team training completed

---

**🎉 Congratulations! Your Enhanced Order Prediction Solution is now deployed and ready to use.**

For additional support, refer to the main README.md file or contact your AWS solutions architect.
