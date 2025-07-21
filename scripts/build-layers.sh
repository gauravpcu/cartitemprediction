#!/bin/bash

# Lambda Layer Build Script
# Creates optimized Lambda layers with size validation

set -e

# Configuration
MAX_LAYER_SIZE_MB=100
MAX_AWS_LAYER_SIZE_MB=50
PYTHON_VERSION="3.9"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Function to calculate directory size in MB
get_size_mb() {
    local dir="$1"
    if [ -d "$dir" ]; then
        du -sm "$dir" | cut -f1
    else
        echo "0"
    fi
}

# Function to validate layer size
validate_layer_size() {
    local layer_dir="$1"
    local layer_name="$2"
    local max_size="$3"
    
    local size_mb=$(get_size_mb "$layer_dir")
    
    log_info "Layer '$layer_name' size: ${size_mb}MB (limit: ${max_size}MB)"
    
    if [ "$size_mb" -gt "$max_size" ]; then
        log_error "Layer '$layer_name' exceeds size limit: ${size_mb}MB > ${max_size}MB"
        return 1
    fi
    
    log_info "Layer '$layer_name' size validation passed"
    return 0
}

# Function to optimize layer by removing unnecessary files
optimize_layer() {
    local layer_dir="$1"
    local layer_name="$2"
    
    log_info "Optimizing layer: $layer_name"
    
    # Remove common unnecessary files and directories
    find "$layer_dir" -type f -name "*.pyc" -delete
    find "$layer_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$layer_dir" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
    find "$layer_dir" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
    find "$layer_dir" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
    find "$layer_dir" -type f -name "*.md" -delete 2>/dev/null || true
    find "$layer_dir" -type f -name "*.txt" -not -name "requirements.txt" -delete 2>/dev/null || true
    find "$layer_dir" -type f -name "*.rst" -delete 2>/dev/null || true
    
    # Remove documentation directories (but preserve botocore.docs for AWS utilities)
    if [ "$layer_name" != "aws-utilities" ]; then
        find "$layer_dir" -type d -name "docs" -exec rm -rf {} + 2>/dev/null || true
        find "$layer_dir" -type d -name "doc" -exec rm -rf {} + 2>/dev/null || true
    fi
    find "$layer_dir" -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true
    find "$layer_dir" -type d -name "example" -exec rm -rf {} + 2>/dev/null || true
    
    # Remove development and build files
    find "$layer_dir" -type f -name "*.c" -delete 2>/dev/null || true
    find "$layer_dir" -type f -name "*.h" -delete 2>/dev/null || true
    find "$layer_dir" -type f -name "*.pyx" -delete 2>/dev/null || true
    find "$layer_dir" -type f -name "*.pxd" -delete 2>/dev/null || true
    
    log_info "Layer optimization completed for: $layer_name"
}

# Function to build a single layer
build_layer() {
    local layer_name="$1"
    local max_size="$2"
    
    log_info "Building layer: $layer_name"
    
    local layer_dir="layers/$layer_name"
    local build_dir="$layer_dir/python"
    local requirements_file="$layer_dir/requirements.txt"
    
    # Check if requirements file exists
    if [ ! -f "$requirements_file" ]; then
        log_error "Requirements file not found: $requirements_file"
        return 1
    fi
    
    # Clean previous build
    if [ -d "$build_dir" ]; then
        log_info "Cleaning previous build for $layer_name"
        rm -rf "$build_dir"
    fi
    
    # Create build directory
    mkdir -p "$build_dir"
    
    # Install dependencies
    log_info "Installing dependencies for $layer_name"
    
    # Install dependencies with correct platform targeting for Lambda
    log_info "Installing dependencies with Linux x86_64 platform targeting"
    pip3 install -r "$requirements_file" -t "$build_dir" \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --no-deps \
        --implementation cp \
        --python-version 3.9 \
        --abi cp39 || {
        log_warn "Failed with platform-specific install, trying with dependencies"
        pip3 install -r "$requirements_file" -t "$build_dir" \
            --platform manylinux2014_x86_64 \
            --only-binary=:all: \
            --implementation cp \
            --python-version 3.9 \
            --abi cp39
    }
    
    # Optimize the layer
    optimize_layer "$build_dir" "$layer_name"
    
    # Validate size
    if ! validate_layer_size "$build_dir" "$layer_name" "$max_size"; then
        log_error "Layer $layer_name failed size validation"
        return 1
    fi
    
    log_info "Successfully built layer: $layer_name"
    return 0
}

# Main execution
main() {
    log_info "Starting Lambda layer build process"
    
    # Check if Python and pip are available
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 is required but not installed"
        exit 1
    fi
    
    # Create layers directory if it doesn't exist
    mkdir -p layers
    
    # Build each layer
    local failed_layers=()
    
    # Build Core Data Science Layer
    if ! build_layer "core-data-science" "$MAX_LAYER_SIZE_MB"; then
        failed_layers+=("core-data-science")
    fi
    
    # Build ML Libraries Layer
    if ! build_layer "ml-libraries" "$MAX_LAYER_SIZE_MB"; then
        failed_layers+=("ml-libraries")
    fi
    
    # Build AWS Utilities Layer
    if ! build_layer "aws-utilities" "$MAX_AWS_LAYER_SIZE_MB"; then
        failed_layers+=("aws-utilities")
    fi
    
    # Report results
    if [ ${#failed_layers[@]} -eq 0 ]; then
        log_info "All layers built successfully!"
        
        # Display final sizes
        echo ""
        log_info "Final layer sizes:"
        for layer in "core-data-science" "ml-libraries" "aws-utilities"; do
            local size=$(get_size_mb "layers/$layer/python")
            echo "  - $layer: ${size}MB"
        done
        
        exit 0
    else
        log_error "Failed to build layers: ${failed_layers[*]}"
        exit 1
    fi
}

# Run main function
main "$@"