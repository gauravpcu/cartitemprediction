#!/bin/bash

# Automated Build Script for Lambda Layers and Functions
# Builds all layers in correct order with size validation and error handling

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
LAYERS_DIR="$PROJECT_ROOT/layers"
FUNCTIONS_DIR="$PROJECT_ROOT/functions"

# Size limits (MB)
MAX_LAYER_SIZE_MB=100
MAX_AWS_LAYER_SIZE_MB=50
MAX_FUNCTION_SIZE_MB=250

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

# Function to display help
show_help() {
    cat << EOF
Automated Build Script for Lambda Layers and Functions

Usage: $0 [OPTIONS]

Options:
    --layers-only       Build only Lambda layers
    --functions-only    Build only Lambda functions
    --skip-validation   Skip size validation checks
    --clean             Clean all build artifacts before building
    --verbose           Enable verbose output
    --help              Show this help message

Build Order:
    1. Core Data Science Layer (pandas, numpy)
    2. ML Libraries Layer (scikit-learn, joblib)
    3. AWS Utilities Layer (boto3, botocore)
    4. Lambda Functions (with layer dependencies)

Size Limits:
    - Core Data Science Layer: ${MAX_LAYER_SIZE_MB}MB
    - ML Libraries Layer: ${MAX_LAYER_SIZE_MB}MB
    - AWS Utilities Layer: ${MAX_AWS_LAYER_SIZE_MB}MB
    - Lambda Functions: ${MAX_FUNCTION_SIZE_MB}MB

Examples:
    $0                      # Build everything
    $0 --layers-only        # Build only layers
    $0 --clean --verbose    # Clean and build with verbose output

EOF
}

# Function to calculate directory size in MB
get_size_mb() {
    local dir="$1"
    if [ -d "$dir" ]; then
        du -sm "$dir" 2>/dev/null | cut -f1 || echo "0"
    else
        echo "0"
    fi
}

# Function to validate prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    local missing_tools=()
    
    # Check Python 3
    if ! command -v python3 &> /dev/null; then
        missing_tools+=("python3")
    fi
    
    # Check pip
    if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
        missing_tools+=("pip")
    fi
    
    # Check AWS SAM CLI
    if ! command -v sam &> /dev/null; then
        missing_tools+=("sam")
    fi
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install the missing tools and try again"
        return 1
    fi
    
    log_info "Prerequisites check passed"
    return 0
}

# Function to clean build artifacts
clean_build_artifacts() {
    log_info "Cleaning build artifacts..."
    
    # Clean layer build directories
    for layer in core-data-science ml-libraries aws-utilities; do
        local layer_python_dir="$LAYERS_DIR/$layer/python"
        if [ -d "$layer_python_dir" ]; then
            log_debug "Removing $layer_python_dir"
            rm -rf "$layer_python_dir"
        fi
    done
    
    # Clean SAM build directory
    if [ -d ".aws-sam" ]; then
        log_debug "Removing .aws-sam directory"
        rm -rf ".aws-sam"
    fi
    
    # Clean Python cache files
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    
    log_info "Build artifacts cleaned"
}

# Function to validate layer size
validate_layer_size() {
    local layer_name="$1"
    local layer_dir="$2"
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

# Function to optimize layer
optimize_layer() {
    local layer_name="$1"
    local layer_dir="$2"
    
    log_info "Optimizing layer: $layer_name"
    
    # Use Python utility for advanced optimization
    if [ -f "$SCRIPT_DIR/scripts/layer-utils.py" ]; then
        if [ "$VERBOSE" = "true" ]; then
            python3 "$SCRIPT_DIR/scripts/layer-utils.py" optimize --layer "$layer_name" --verbose
        else
            python3 "$SCRIPT_DIR/scripts/layer-utils.py" optimize --layer "$layer_name"
        fi
    else
        # Fallback to basic optimization
        log_debug "Using basic optimization for $layer_name"
        
        # Remove common unnecessary files and directories
        find "$layer_dir" -type f -name "*.pyc" -delete 2>/dev/null || true
        find "$layer_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find "$layer_dir" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
        find "$layer_dir" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
        find "$layer_dir" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
        find "$layer_dir" -type f -name "*.md" -delete 2>/dev/null || true
        find "$layer_dir" -type f -name "*.txt" -not -name "requirements.txt" -delete 2>/dev/null || true
        find "$layer_dir" -type f -name "*.rst" -delete 2>/dev/null || true
        find "$layer_dir" -type d -name "docs" -exec rm -rf {} + 2>/dev/null || true
        find "$layer_dir" -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true
    fi
    
    log_info "Layer optimization completed for: $layer_name"
}

# Function to validate layer imports
validate_layer_imports() {
    local layer_name="$1"
    
    log_info "Validating imports for layer: $layer_name"
    
    if [ -f "$SCRIPT_DIR/scripts/layer-utils.py" ]; then
        if [ "$VERBOSE" = "true" ]; then
            python3 "$SCRIPT_DIR/scripts/layer-utils.py" validate --layer "$layer_name" --verbose
        else
            python3 "$SCRIPT_DIR/scripts/layer-utils.py" validate --layer "$layer_name"
        fi
    else
        log_warn "Layer validation utility not found, skipping import validation"
        return 0
    fi
}

# Function to build a single layer
build_layer() {
    local layer_name="$1"
    local max_size="$2"
    
    log_info "Building layer: $layer_name"
    
    # Log build start event
    if [ -f "$SCRIPT_DIR/scripts/deployment-monitor.py" ]; then
        python3 "$SCRIPT_DIR/scripts/deployment-monitor.py" monitor --workspace "$PROJECT_ROOT" &
    fi
    
    local layer_dir="$LAYERS_DIR/$layer_name"
    local build_dir="$layer_dir/python"
    local requirements_file="$layer_dir/requirements.txt"
    
    # Check if requirements file exists
    if [ ! -f "$requirements_file" ]; then
        log_error "Requirements file not found: $requirements_file"
        return 1
    fi
    
    # Clean previous build
    if [ -d "$build_dir" ]; then
        log_debug "Cleaning previous build for $layer_name"
        rm -rf "$build_dir"
    fi
    
    # Create build directory
    mkdir -p "$build_dir"
    
    # Install dependencies
    log_info "Installing dependencies for $layer_name"
    
    # Use pip command (prefer pip3 if available)
    local pip_cmd="pip"
    if command -v pip3 &> /dev/null; then
        pip_cmd="pip3"
    fi
    
    # Try platform-specific install first, fallback to standard install
    if ! $pip_cmd install -r "$requirements_file" -t "$build_dir" --no-deps --platform manylinux2014_x86_64 --only-binary=:all: 2>/dev/null; then
        log_warn "Platform-specific install failed, trying standard install"
        if ! $pip_cmd install -r "$requirements_file" -t "$build_dir"; then
            log_error "Failed to install dependencies for $layer_name"
            return 1
        fi
    fi
    
    # Optimize the layer
    optimize_layer "$layer_name" "$build_dir"
    
    # Validate size if not skipped
    if [ "$SKIP_VALIDATION" != "true" ]; then
        if ! validate_layer_size "$layer_name" "$build_dir" "$max_size"; then
            log_error "Layer $layer_name failed size validation"
            return 1
        fi
        
        # Validate imports
        if ! validate_layer_imports "$layer_name"; then
            log_error "Layer $layer_name failed import validation"
            return 1
        fi
    fi
    
    log_info "Successfully built layer: $layer_name"
    
    # Run size validation using the comprehensive validator
    if [ "$SKIP_VALIDATION" != "true" ] && [ -f "$SCRIPT_DIR/scripts/size-validation.py" ]; then
        log_info "Running comprehensive size validation for $layer_name"
        if ! python3 "$SCRIPT_DIR/scripts/size-validation.py" validate --target layers --verbose; then
            log_error "Comprehensive size validation failed for $layer_name"
            return 1
        fi
    fi
    
    return 0
}

# Function to build all layers
build_layers() {
    log_info "Building Lambda layers in dependency order..."
    
    local failed_layers=()
    
    # Build layers in dependency order
    # 1. Core Data Science Layer (base dependencies)
    if ! build_layer "core-data-science" "$MAX_LAYER_SIZE_MB"; then
        failed_layers+=("core-data-science")
    fi
    
    # 2. ML Libraries Layer (depends on numpy from core-data-science)
    if ! build_layer "ml-libraries" "$MAX_LAYER_SIZE_MB"; then
        failed_layers+=("ml-libraries")
    fi
    
    # 3. AWS Utilities Layer (independent)
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
            local size=$(get_size_mb "$LAYERS_DIR/$layer/python")
            echo "  - $layer: ${size}MB"
        done
        
        return 0
    else
        log_error "Failed to build layers: ${failed_layers[*]}"
        return 1
    fi
}

# Function to validate function size
validate_function_size() {
    local function_name="$1"
    local function_dir="$2"
    
    local size_mb=$(get_size_mb "$function_dir")
    
    log_info "Function '$function_name' size: ${size_mb}MB (limit: ${MAX_FUNCTION_SIZE_MB}MB)"
    
    if [ "$size_mb" -gt "$MAX_FUNCTION_SIZE_MB" ]; then
        log_error "Function '$function_name' exceeds size limit: ${size_mb}MB > ${MAX_FUNCTION_SIZE_MB}MB"
        return 1
    fi
    
    log_info "Function '$function_name' size validation passed"
    return 0
}

# Function to build Lambda functions
build_functions() {
    log_info "Building Lambda functions..."
    
    # Use SAM to build functions
    log_info "Running SAM build..."
    
    if [ "$VERBOSE" = "true" ]; then
        sam build --debug
    else
        sam build
    fi
    
    if [ $? -ne 0 ]; then
        log_error "SAM build failed"
        return 1
    fi
    
    # Validate function sizes if not skipped
    if [ "$SKIP_VALIDATION" != "true" ]; then
        log_info "Validating function sizes..."
        
        local build_dir=".aws-sam/build"
        local failed_functions=()
        
        # Check each function directory in the build output
        if [ -d "$build_dir" ]; then
            for function_dir in "$build_dir"/*Function; do
                if [ -d "$function_dir" ]; then
                    local function_name=$(basename "$function_dir")
                    if ! validate_function_size "$function_name" "$function_dir"; then
                        failed_functions+=("$function_name")
                    fi
                fi
            done
        fi
        
        if [ ${#failed_functions[@]} -gt 0 ]; then
            log_error "Functions failed size validation: ${failed_functions[*]}"
            return 1
        fi
    fi
    
    log_info "Lambda functions built successfully!"
    return 0
}

# Function to display build summary
display_build_summary() {
    echo ""
    log_info "Build Summary"
    echo "=============================================="
    
    # Layer summary
    echo ""
    echo "Lambda Layers:"
    for layer in "core-data-science" "ml-libraries" "aws-utilities"; do
        local layer_dir="$LAYERS_DIR/$layer/python"
        if [ -d "$layer_dir" ]; then
            local size=$(get_size_mb "$layer_dir")
            echo "  ✓ $layer: ${size}MB"
        else
            echo "  ✗ $layer: Not built"
        fi
    done
    
    # Function summary
    echo ""
    echo "Lambda Functions:"
    local build_dir=".aws-sam/build"
    if [ -d "$build_dir" ]; then
        for function_dir in "$build_dir"/*Function; do
            if [ -d "$function_dir" ]; then
                local function_name=$(basename "$function_dir")
                local size=$(get_size_mb "$function_dir")
                echo "  ✓ $function_name: ${size}MB"
            fi
        done
    else
        echo "  ✗ Functions: Not built"
    fi
    
    echo ""
    log_info "Build completed successfully!"
}

# Main execution function
main() {
    local build_layers_only=false
    local build_functions_only=false
    local clean_first=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --layers-only)
                build_layers_only=true
                shift
                ;;
            --functions-only)
                build_functions_only=true
                shift
                ;;
            --skip-validation)
                SKIP_VALIDATION="true"
                shift
                ;;
            --clean)
                clean_first=true
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
    
    # Validate mutually exclusive options
    if [ "$build_layers_only" = "true" ] && [ "$build_functions_only" = "true" ]; then
        log_error "Cannot specify both --layers-only and --functions-only"
        exit 1
    fi
    
    log_info "Starting automated build process..."
    
    # Check prerequisites
    if ! check_prerequisites; then
        exit 1
    fi
    
    # Clean if requested
    if [ "$clean_first" = "true" ]; then
        clean_build_artifacts
    fi
    
    # Build based on options
    if [ "$build_functions_only" = "true" ]; then
        # Build only functions
        if ! build_functions; then
            log_error "Function build failed"
            exit 1
        fi
    elif [ "$build_layers_only" = "true" ]; then
        # Build only layers
        if ! build_layers; then
            log_error "Layer build failed"
            exit 1
        fi
    else
        # Build everything (layers first, then functions)
        if ! build_layers; then
            log_error "Layer build failed"
            exit 1
        fi
        
        if ! build_functions; then
            log_error "Function build failed"
            exit 1
        fi
    fi
    
    # Display summary
    display_build_summary
    
    log_info "Automated build completed successfully!"
}

# Run main function with all arguments
main "$@"