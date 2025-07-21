#!/bin/bash

# Build optimized AWS utilities layer with selective service inclusion
# This script creates a minimal boto3 installation with only required services

set -e

LAYER_DIR="layers/aws-utilities"
PYTHON_DIR="$LAYER_DIR/python"
TEMP_DIR="/tmp/aws-utilities-build"

echo "Building optimized AWS utilities layer..."

# Clean up previous builds
rm -rf "$PYTHON_DIR"
rm -rf "$TEMP_DIR"
mkdir -p "$PYTHON_DIR"
mkdir -p "$TEMP_DIR"

# Install full boto3 in temp directory first
echo "Installing boto3 dependencies..."
python3 -m pip install -r "$LAYER_DIR/requirements.txt" -t "$TEMP_DIR" --no-cache-dir

# Copy core boto3 and botocore files
echo "Copying core boto3 files..."
cp -r "$TEMP_DIR/boto3" "$PYTHON_DIR/"
cp -r "$TEMP_DIR/botocore" "$PYTHON_DIR/"

# Copy other required dependencies
echo "Copying supporting libraries..."
cp -r "$TEMP_DIR/dateutil" "$PYTHON_DIR/" 2>/dev/null || true
cp -r "$TEMP_DIR/jmespath" "$PYTHON_DIR/" 2>/dev/null || true
cp -r "$TEMP_DIR/urllib3" "$PYTHON_DIR/" 2>/dev/null || true
cp -r "$TEMP_DIR/s3transfer" "$PYTHON_DIR/" 2>/dev/null || true
cp "$TEMP_DIR/six.py" "$PYTHON_DIR/" 2>/dev/null || true

# Define required AWS services based on function analysis
REQUIRED_SERVICES=(
    "s3"
    "dynamodb" 
    "lambda"
    "sagemaker-runtime"
    "bedrock-runtime"
    "sts"  # Required for authentication
    "ec2"  # Required for VPC operations if needed
)

echo "Optimizing boto3 services..."

# Remove unused service data files from botocore
BOTOCORE_DATA_DIR="$PYTHON_DIR/botocore/data"
if [ -d "$BOTOCORE_DATA_DIR" ]; then
    echo "Removing unused AWS service definitions..."
    
    # Keep only required services
    for service_dir in "$BOTOCORE_DATA_DIR"/*; do
        if [ -d "$service_dir" ]; then
            service_name=$(basename "$service_dir")
            keep_service=false
            
            for required in "${REQUIRED_SERVICES[@]}"; do
                if [[ "$service_name" == "$required" ]] || [[ "$service_name" == *"$required"* ]]; then
                    keep_service=true
                    break
                fi
            done
            
            if [ "$keep_service" = false ]; then
                echo "  Removing service: $service_name"
                rm -rf "$service_dir"
            else
                echo "  Keeping service: $service_name"
            fi
        fi
    done
fi

# Remove unnecessary files to reduce size
echo "Removing unnecessary files..."

# Remove Python cache files more aggressively
echo "Removing Python cache files..."
find "$PYTHON_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$PYTHON_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove __pycache__ directories with multiple approaches
echo "Removing __pycache__ directories..."
# First approach - depth first
find "$PYTHON_DIR" -depth -type d -name "__pycache__" -exec rm -rf {} \; 2>/dev/null || true
# Second approach - using while loop for stubborn directories
find "$PYTHON_DIR" -type d -name "__pycache__" | while read dir; do
    if [ -d "$dir" ]; then
        rm -rf "$dir" 2>/dev/null || true
    fi
done

# Remove test files and documentation
find "$PYTHON_DIR" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "$PYTHON_DIR" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
find "$PYTHON_DIR" -type f -name "*.md" -delete 2>/dev/null || true
find "$PYTHON_DIR" -type f -name "*.rst" -delete 2>/dev/null || true
find "$PYTHON_DIR" -type f -name "*.txt" -delete 2>/dev/null || true

# Remove examples directories but keep essential docs
find "$PYTHON_DIR" -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true
# Keep both boto3/docs and botocore/docs as they are required for functionality
# Note: botocore.docs is required for boto3 to function properly

# Remove .dist-info directories to save space
find "$PYTHON_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

# Calculate and display size
echo "Calculating layer size..."
LAYER_SIZE=$(du -sh "$PYTHON_DIR" | cut -f1)
LAYER_SIZE_MB=$(du -sm "$PYTHON_DIR" | cut -f1)

echo "AWS utilities layer built successfully!"
echo "Layer size: $LAYER_SIZE (${LAYER_SIZE_MB}MB)"

# Check if size is under target (50MB)
if [ "$LAYER_SIZE_MB" -gt 50 ]; then
    echo "WARNING: Layer size (${LAYER_SIZE_MB}MB) exceeds target of 50MB"
    echo "Consider removing more services or optimizing further"
else
    echo "SUCCESS: Layer size is within 50MB target"
fi

# Clean up temp directory
rm -rf "$TEMP_DIR"

echo "Build complete. Layer ready at: $PYTHON_DIR"