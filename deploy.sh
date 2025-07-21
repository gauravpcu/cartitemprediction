#!/bin/bash

# Enhanced Order Prediction Solution Deployment Script
# This script deploys the complete solution using AWS SAM with optimized layers

set -e

# Configuration
STACK_NAME="item-prediction"
REGION="us-east-1"
ENVIRONMENT="dev"
BEDROCK_MODEL="anthropic.claude-3-sonnet-20240229-v1:0"
SAGEMAKER_ENDPOINT_NAME="hybrent-deepar-2025-07-20-23-56-22-287"
ENABLE_PRODUCT_FORECASTING="true"

# Deployment options
BUILD_LAYERS="true"
SKIP_SIZE_VALIDATION="false"
ENABLE_ROLLBACK="true"
BACKUP_STACK_NAME=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

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

# Function to display help
show_help() {
    cat << EOF
Enhanced Order Prediction Solution Deployment Script

Usage: $0 [OPTIONS]

Configuration Options:
  --stack-name NAME              CloudFormation stack name (default: item-prediction)
  --region REGION                AWS region (default: us-east-1)
  --environment ENV              Environment (dev/test/prod, default: dev)
  --bedrock-model MODEL          Bedrock model ID (default: $BEDROCK_MODEL)
  --sagemaker-endpoint-name NAME SageMaker endpoint name (default: $SAGEMAKER_ENDPOINT_NAME)
  --disable-product-forecasting  Disable product-level forecasting

Build Options:
  --skip-layer-build             Skip building Lambda layers (use existing)
  --skip-size-validation         Skip pre-deployment size validation
  --disable-rollback             Disable automatic rollback on failure

Deployment Options:
  --guided                       Use guided deployment (interactive)
  --verbose                      Enable verbose output
  --help                         Show this help message

Examples:
  $0                                    # Standard deployment
  $0 --skip-layer-build                 # Deploy without rebuilding layers
  $0 --environment prod --guided        # Production deployment with guidance
  $0 --disable-rollback --verbose       # Deploy with verbose output, no rollback

EOF
}

# Function to create stack backup
create_stack_backup() {
    local stack_name="$1"
    
    log_info "Creating stack backup before deployment..."
    
    # Check if stack exists
    if ! aws cloudformation describe-stacks --stack-name "$stack_name" --region "$REGION" &> /dev/null; then
        log_info "Stack does not exist, no backup needed"
        return 0
    fi
    
    # Generate backup name with timestamp
    local timestamp=$(date +"%Y%m%d-%H%M%S")
    BACKUP_STACK_NAME="${stack_name}-backup-${timestamp}"
    
    # Get current stack template
    local template_file="/tmp/${stack_name}-backup-template.json"
    
    if aws cloudformation get-template --stack-name "$stack_name" --region "$REGION" --query 'TemplateBody' > "$template_file" 2>/dev/null; then
        log_info "Stack template backed up to: $template_file"
        log_info "Backup stack name would be: $BACKUP_STACK_NAME"
        return 0
    else
        log_warn "Failed to backup stack template, continuing without backup"
        ENABLE_ROLLBACK="false"
        return 1
    fi
}

# Function to rollback deployment
rollback_deployment() {
    local stack_name="$1"
    local reason="$2"
    
    if [ "$ENABLE_ROLLBACK" != "true" ]; then
        log_warn "Rollback disabled, manual intervention required"
        return 1
    fi
    
    log_error "Deployment failed: $reason"
    log_info "Initiating rollback..."
    
    # Check if stack exists and is in a rollback-able state
    local stack_status=$(aws cloudformation describe-stacks --stack-name "$stack_name" --region "$REGION" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")
    
    case "$stack_status" in
        "UPDATE_FAILED"|"UPDATE_ROLLBACK_FAILED"|"CREATE_FAILED")
            log_info "Attempting to rollback stack..."
            if aws cloudformation cancel-update-stack --stack-name "$stack_name" --region "$REGION" 2>/dev/null; then
                log_info "Stack rollback initiated"
                
                # Wait for rollback to complete
                log_info "Waiting for rollback to complete..."
                aws cloudformation wait stack-update-complete --stack-name "$stack_name" --region "$REGION" || true
                
                local final_status=$(aws cloudformation describe-stacks --stack-name "$stack_name" --region "$REGION" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "UNKNOWN")
                log_info "Final stack status after rollback: $final_status"
            else
                log_error "Failed to initiate stack rollback"
            fi
            ;;
        "NOT_FOUND")
            log_info "Stack does not exist, no rollback needed"
            ;;
        *)
            log_warn "Stack in state '$stack_status', rollback may not be applicable"
            ;;
    esac
}

# Function to validate deployment prerequisites
validate_deployment_prerequisites() {
    log_info "Validating deployment prerequisites..."
    
    # Check if layers are built (unless skipping layer build)
    if [ "$BUILD_LAYERS" = "true" ]; then
        local layers_dir="layers"
        local required_layers=("core-data-science" "ml-libraries" "aws-utilities")
        
        for layer in "${required_layers[@]}"; do
            local layer_python_dir="$layers_dir/$layer/python"
            if [ ! -d "$layer_python_dir" ]; then
                log_error "Layer '$layer' not built. Run build process first or use --skip-layer-build"
                return 1
            fi
        done
        
        log_info "All required layers are available"
    fi
    
    # Validate SAM build output exists
    if [ ! -d ".aws-sam/build" ]; then
        log_error "SAM build output not found. Build process must complete successfully first."
        return 1
    fi
    
    log_info "Deployment prerequisites validated"
    return 0
}

# Function to perform pre-deployment size validation
perform_size_validation() {
    if [ "$SKIP_SIZE_VALIDATION" = "true" ]; then
        log_info "Skipping size validation as requested"
        return 0
    fi
    
    log_info "Performing comprehensive pre-deployment size validation..."
    
    # Use the comprehensive size validation script
    if [ -f "scripts/validate-deployment-size.sh" ]; then
        if ! ./scripts/validate-deployment-size.sh; then
            log_error "Comprehensive size validation failed"
            return 1
        fi
        return 0
    fi
    
    # Fallback to basic validation
    log_warn "Comprehensive validation script not found, using basic validation..."
    
    local validation_failed=false
    
    # Validate layer sizes
    local layers_dir="layers"
    declare -A layer_limits=([core-data-science]=100 [ml-libraries]=100 [aws-utilities]=50)
    
    for layer in "${!layer_limits[@]}"; do
        local layer_python_dir="$layers_dir/$layer/python"
        if [ -d "$layer_python_dir" ]; then
            local size_mb=$(du -sm "$layer_python_dir" 2>/dev/null | cut -f1 || echo "0")
            local limit_mb=${layer_limits[$layer]}
            
            log_info "Layer '$layer': ${size_mb}MB (limit: ${limit_mb}MB)"
            
            if [ "$size_mb" -gt "$limit_mb" ]; then
                log_error "Layer '$layer' exceeds size limit: ${size_mb}MB > ${limit_mb}MB"
                validation_failed=true
            fi
        fi
    done
    
    # Validate function sizes
    local build_dir=".aws-sam/build"
    local function_limit_mb=250
    
    if [ -d "$build_dir" ]; then
        for function_dir in "$build_dir"/*Function; do
            if [ -d "$function_dir" ]; then
                local function_name=$(basename "$function_dir")
                local size_mb=$(du -sm "$function_dir" 2>/dev/null | cut -f1 || echo "0")
                
                log_info "Function '$function_name': ${size_mb}MB (limit: ${function_limit_mb}MB)"
                
                if [ "$size_mb" -gt "$function_limit_mb" ]; then
                    log_error "Function '$function_name' exceeds size limit: ${size_mb}MB > ${function_limit_mb}MB"
                    validation_failed=true
                fi
            fi
        done
    fi
    
    if [ "$validation_failed" = "true" ]; then
        log_error "Size validation failed. Deployment aborted."
        log_error "Run optimization process or use --skip-size-validation to override"
        return 1
    fi
    
    log_info "Size validation passed"
    return 0
}

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
        --skip-layer-build)
            BUILD_LAYERS="false"
            shift
            ;;
        --skip-size-validation)
            SKIP_SIZE_VALIDATION="true"
            shift
            ;;
        --disable-rollback)
            ENABLE_ROLLBACK="false"
            shift
            ;;
        --guided)
            GUIDED_DEPLOYMENT="true"
            shift
            ;;
        --verbose)
            VERBOSE="true"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

log_info "Deployment Configuration:"
echo "  Stack Name: $STACK_NAME"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"
echo "  Bedrock Model: $BEDROCK_MODEL"
echo "  SageMaker Endpoint: $SAGEMAKER_ENDPOINT_NAME"
echo "  Product Forecasting: $ENABLE_PRODUCT_FORECASTING"
echo "  Build Layers: $BUILD_LAYERS"
echo "  Skip Size Validation: $SKIP_SIZE_VALIDATION"
echo "  Enable Rollback: $ENABLE_ROLLBACK"
echo ""

# Create stack backup if rollback is enabled
if [ "$ENABLE_ROLLBACK" = "true" ]; then
    create_stack_backup "$STACK_NAME"
fi

# Build layers and application
if [ "$BUILD_LAYERS" = "true" ]; then
    log_info "Building optimized Lambda layers and functions..."
    
    # Use our automated build script
    build_args=""
    if [ "$VERBOSE" = "true" ]; then
        build_args="--verbose"
    fi
    if [ "$SKIP_SIZE_VALIDATION" = "true" ]; then
        build_args="$build_args --skip-validation"
    fi
    
    if ! ./build.sh $build_args; then
        rollback_deployment "$STACK_NAME" "Build process failed"
        exit 1
    fi
else
    log_info "Skipping layer build, using existing layers..."
    
    # Still need to build functions with SAM
    log_info "Building SAM application..."
    if [ "$VERBOSE" = "true" ]; then
        sam build --region "$REGION" --debug
    else
        sam build --region "$REGION"
    fi
    
    if [ $? -ne 0 ]; then
        rollback_deployment "$STACK_NAME" "SAM build failed"
        exit 1
    fi
fi

log_info "Build completed successfully"

# Validate deployment prerequisites
if ! validate_deployment_prerequisites; then
    rollback_deployment "$STACK_NAME" "Deployment prerequisites validation failed"
    exit 1
fi

# Perform pre-deployment size validation
if ! perform_size_validation; then
    rollback_deployment "$STACK_NAME" "Size validation failed"
    exit 1
fi

# Deploy the application
log_info "Deploying SAM application..."

# Prepare deployment command arguments
deploy_args=(
    --stack-name "$STACK_NAME"
    --region "$REGION"
    --capabilities CAPABILITY_IAM
    --parameter-overrides
        Environment="$ENVIRONMENT"
        BedrockModelId="$BEDROCK_MODEL"
        SageMakerEndpointName="$SAGEMAKER_ENDPOINT_NAME"
        EnableProductLevelForecasting="$ENABLE_PRODUCT_FORECASTING"
    --resolve-s3
)

# Add verbose flag if requested
if [ "$VERBOSE" = "true" ]; then
    deploy_args+=(--debug)
fi

# Check if this is first deployment or if guided deployment is requested
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &> /dev/null || [ "$GUIDED_DEPLOYMENT" = "true" ]; then
    log_info "Using guided deployment..."
    deploy_args+=(--guided)
fi

# Execute deployment with error handling
log_info "Executing SAM deployment..."
if ! sam deploy "${deploy_args[@]}"; then
    rollback_deployment "$STACK_NAME" "SAM deployment failed"
    exit 1
fi

log_info "SAM deployment completed successfully"

# Run post-deployment validation
log_info "Running post-deployment validation tests..."
if [ -f "scripts/post-deployment-validation.py" ]; then
    validation_report="reports/post-deployment-validation-$(date +%Y%m%d-%H%M%S).json"
    mkdir -p reports
    
    if python3 scripts/post-deployment-validation.py --stack-name "$STACK_NAME" --region "$REGION" --output "$validation_report"; then
        log_info "Post-deployment validation passed"
        log_info "Validation report saved to: $validation_report"
    else
        log_warn "Post-deployment validation failed, but deployment may still be functional"
        log_warn "Check the validation report for details: $validation_report"
    fi
else
    log_warn "Post-deployment validation script not found, skipping validation tests"
fi

# Verify deployment success
log_info "Verifying deployment success..."

# Check final stack status
final_status=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "UNKNOWN")

case "$final_status" in
    "CREATE_COMPLETE"|"UPDATE_COMPLETE")
        log_info "Stack deployment successful: $final_status"
        ;;
    *)
        log_error "Stack deployment may have issues: $final_status"
        rollback_deployment "$STACK_NAME" "Deployment verification failed"
        exit 1
        ;;
esac

# Get stack outputs
log_info "Retrieving stack outputs..."
outputs_json=""
if outputs_json=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs' \
    --output json 2>/dev/null); then
    
    # Extract key outputs
    api_endpoint=$(echo "$outputs_json" | jq -r '.[] | select(.OutputKey=="ApiEndpoint") | .OutputValue // "Not Available"')
    product_endpoint=$(echo "$outputs_json" | jq -r '.[] | select(.OutputKey=="ProductPredictionEndpoint") | .OutputValue // "Not Available"')
    raw_bucket=$(echo "$outputs_json" | jq -r '.[] | select(.OutputKey=="RawDataBucketName") | .OutputValue // "Not Available"')
    processed_bucket=$(echo "$outputs_json" | jq -r '.[] | select(.OutputKey=="ProcessedDataBucketName") | .OutputValue // "Not Available"')
    
    # Display deployment summary
    echo ""
    log_info "🎉 Deployment completed successfully!"
    echo "=================================================="
    echo ""
    echo "📋 Deployment Summary:"
    echo "  Stack Name: $STACK_NAME"
    echo "  Region: $REGION"
    echo "  Environment: $ENVIRONMENT"
    echo "  Status: $final_status"
    echo ""
    echo "🌐 API Endpoints:"
    echo "  Main API: $api_endpoint"
    echo "  Product Predictions: $product_endpoint"
    echo ""
    echo "🪣 S3 Buckets:"
    echo "  Raw Data: $raw_bucket"
    echo "  Processed Data: $processed_bucket"
    echo ""
    echo "📊 Layer Information:"
    layers_dir="layers"
    for layer in core-data-science ml-libraries aws-utilities; do
        layer_python_dir="$layers_dir/$layer/python"
        if [ -d "$layer_python_dir" ]; then
            size_mb=$(du -sm "$layer_python_dir" 2>/dev/null | cut -f1 || echo "0")
            echo "  $layer: ${size_mb}MB"
        fi
    done
    echo ""
    echo "📝 Next Steps:"
    echo "1. Upload your historical order data to: s3://$raw_bucket/"
    echo "2. Wait for data processing to complete"
    echo "3. Test the API endpoints using the provided examples"
    echo "4. Monitor CloudWatch logs for any issues"
    echo ""
    echo "🔗 Useful Commands:"
    echo "  View logs: sam logs --stack-name $STACK_NAME --region $REGION"
    echo "  Delete stack: sam delete --stack-name $STACK_NAME --region $REGION"
    echo "  Rebuild layers: ./build.sh --layers-only"
    echo "  Redeploy: ./deploy.sh --skip-layer-build"
    echo ""
    log_info "✨ Happy predicting!"
    
else
    log_warn "Could not retrieve stack outputs, but deployment appears successful"
fi

# Clean up backup references if deployment was successful
if [ -n "$BACKUP_STACK_NAME" ]; then
    log_info "Deployment successful, backup information available if needed"
    log_debug "Backup stack name: $BACKUP_STACK_NAME"
fi
