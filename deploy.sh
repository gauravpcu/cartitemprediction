#!/bin/bash

# Enhanced Order Prediction Solution Deployment Script
# This script deploys the complete solution using AWS SAM

set -e

# Configuration
STACK_NAME="cart-prediction"
REGION="us-east-1"
ENVIRONMENT="dev"
BEDROCK_MODEL="anthropic.claude-3-sonnet-20240229-v1:0"
SAGEMAKER_ENDPOINT_NAME="canvas-PRO-MT-07062025"
ENABLE_PRODUCT_FORECASTING="true"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting Enhanced Order Prediction Solution Deployment${NC}"
echo "=================================================="

# Check prerequisites
echo -e "${YELLOW}📋 Checking prerequisites...${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Check if SAM CLI is installed
if ! command -v sam &> /dev/null; then
    echo -e "${RED}❌ SAM CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured. Please run 'aws configure' first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --bedrock-model)
            BEDROCK_MODEL="$2"
            shift 2
            ;;
        --sagemaker-endpoint-name)
            SAGEMAKER_ENDPOINT_NAME="$2"
            shift 2
            ;;
        --disable-product-forecasting)
            ENABLE_PRODUCT_FORECASTING="false"
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --stack-name NAME              CloudFormation stack name (default: cart-prediction)"
            echo "  --region REGION                AWS region (default: us-east-1)"
            echo "  --environment ENV              Environment (dev/test/prod, default: dev)"
            echo "  --bedrock-model MODEL          Bedrock model ID (default: $BEDROCK_MODEL)"
            echo "  --sagemaker-endpoint-name NAME SageMaker endpoint name (default: $SAGEMAKER_ENDPOINT_NAME)"
            echo "  --disable-product-forecasting  Disable product-level forecasting"
            echo "  --help                         Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${YELLOW}📝 Deployment Configuration:${NC}"
echo "  Stack Name: $STACK_NAME"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"
echo "  Bedrock Model: $BEDROCK_MODEL"
echo "  SageMaker Endpoint: $SAGEMAKER_ENDPOINT_NAME"
echo "  Product Forecasting: $ENABLE_PRODUCT_FORECASTING"
echo ""

# Build the SAM application
echo -e "${YELLOW}🔨 Building SAM application...${NC}"
sam build --region $REGION

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ SAM build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ SAM build completed${NC}"

# Deploy the application
echo -e "${YELLOW}🚀 Deploying SAM application...${NC}"

# Check if this is first deployment or if we need to create S3 bucket
if ! aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &> /dev/null; then
    echo -e "${YELLOW}📦 First deployment detected, using guided deployment...${NC}"
    sam deploy \
        --guided \
        --stack-name $STACK_NAME \
        --region $REGION \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            Environment=$ENVIRONMENT \
            BedrockModelId=$BEDROCK_MODEL \
            SageMakerEndpointName=$SAGEMAKER_ENDPOINT_NAME \
            EnableProductLevelForecasting=$ENABLE_PRODUCT_FORECASTING \
        --resolve-s3
else
    echo -e "${YELLOW}📦 Updating existing deployment...${NC}"
    sam deploy \
        --stack-name $STACK_NAME \
        --region $REGION \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            Environment=$ENVIRONMENT \
            BedrockModelId=$BEDROCK_MODEL \
            SageMakerEndpointName=$SAGEMAKER_ENDPOINT_NAME \
            EnableProductLevelForecasting=$ENABLE_PRODUCT_FORECASTING \
        --resolve-s3
fi

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ SAM deployment failed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ SAM deployment completed${NC}"

# Get stack outputs
echo -e "${YELLOW}📊 Retrieving stack outputs...${NC}"
OUTPUTS=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs' \
    --output json)

API_ENDPOINT=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="ApiEndpoint") | .OutputValue')
PRODUCT_ENDPOINT=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="ProductPredictionEndpoint") | .OutputValue')
RAW_BUCKET=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="RawDataBucketName") | .OutputValue')
PROCESSED_BUCKET=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="ProcessedDataBucketName") | .OutputValue')

echo ""
echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo "=================================================="
echo -e "${YELLOW}📋 Important Information:${NC}"
echo ""
echo "API Endpoints:"
echo "  Main API: $API_ENDPOINT"
echo "  Product Predictions: $PRODUCT_ENDPOINT"
echo ""
echo "S3 Buckets:"
echo "  Raw Data: $RAW_BUCKET"
echo "  Processed Data: $PROCESSED_BUCKET"
echo ""
echo -e "${YELLOW}📝 Next Steps:${NC}"
echo "1. Upload your historical order data to: s3://$RAW_BUCKET/"
echo "2. Wait for data processing to complete"
echo "3. Test the API endpoints using the provided examples"
echo "4. Monitor CloudWatch logs for any issues"
echo ""
echo -e "${YELLOW}🔗 Useful Commands:${NC}"
echo "  View logs: sam logs --stack-name $STACK_NAME --region $REGION"
echo "  Delete stack: sam delete --stack-name $STACK_NAME --region $REGION"
echo ""
echo -e "${GREEN}✨ Happy predicting!${NC}"
