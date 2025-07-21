#!/bin/bash

# Lambda Layer Management Script
# Provides unified interface for building, optimizing, and validating layers

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LAYERS_DIR="$PROJECT_ROOT/layers"

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

# Help function
show_help() {
    cat << EOF
Lambda Layer Management Script

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    build [LAYER]       Build layer(s) - specify layer name or 'all'
    optimize [LAYER]    Optimize layer(s) - specify layer name or 'all'
    validate [LAYER]    Validate layer(s) - specify layer name or 'all'
    report [LAYER]      Generate report for layer(s) - specify layer name or 'all'
    clean [LAYER]       Clean build artifacts for layer(s) - specify layer name or 'all'
    status              Show status of all layers

Layer Names:
    core-data-science   Core data science packages (pandas, numpy)
    ml-libraries        Machine learning packages (scikit-learn, joblib)
    aws-utilities       AWS SDK packages (boto3, botocore)
    all                 All layers

Options:
    -v, --verbose       Enable verbose output
    -h, --help          Show this help message

Examples:
    $0 build all                    # Build all layers
    $0 build core-data-science      # Build specific layer
    $0 optimize ml-libraries        # Optimize ML libraries layer
    $0 validate all                 # Validate all layers
    $0 status                       # Show status of all layers

EOF
}

# Get list of available layers
get_layers() {
    local layer_arg="$1"
    
    if [ "$layer_arg" = "all" ]; then
        echo "core-data-science ml-libraries aws-utilities"
    else
        echo "$layer_arg"
    fi
}

# Check if layer exists
layer_exists() {
    local layer="$1"
    [ -d "$LAYERS_DIR/$layer" ]
}

# Get layer size
get_layer_size() {
    local layer="$1"
    local layer_python_dir="$LAYERS_DIR/$layer/python"
    
    if [ -d "$layer_python_dir" ]; then
        du -sm "$layer_python_dir" 2>/dev/null | cut -f1 || echo "0"
    else
        echo "0"
    fi
}

# Build layers
build_layers() {
    local layers="$1"
    local verbose="$2"
    
    log_info "Building layers: $layers"
    
    if [ "$verbose" = "true" ]; then
        "$SCRIPT_DIR/build-layers.sh" -v
    else
        "$SCRIPT_DIR/build-layers.sh"
    fi
}

# Optimize layers
optimize_layers() {
    local layers="$1"
    local verbose="$2"
    
    for layer in $layers; do
        if ! layer_exists "$layer"; then
            log_error "Layer '$layer' does not exist. Run 'build $layer' first."
            continue
        fi
        
        log_info "Optimizing layer: $layer"
        
        if [ "$verbose" = "true" ]; then
            python3 "$SCRIPT_DIR/layer-utils.py" optimize --layer "$layer" --verbose
        else
            python3 "$SCRIPT_DIR/layer-utils.py" optimize --layer "$layer"
        fi
    done
}

# Validate layers
validate_layers() {
    local layers="$1"
    local verbose="$2"
    local all_valid=true
    
    for layer in $layers; do
        if ! layer_exists "$layer"; then
            log_error "Layer '$layer' does not exist. Run 'build $layer' first."
            all_valid=false
            continue
        fi
        
        log_info "Validating layer: $layer"
        
        if [ "$verbose" = "true" ]; then
            if ! python3 "$SCRIPT_DIR/layer-utils.py" validate --layer "$layer" --verbose; then
                all_valid=false
            fi
        else
            if ! python3 "$SCRIPT_DIR/layer-utils.py" validate --layer "$layer"; then
                all_valid=false
            fi
        fi
    done
    
    if [ "$all_valid" = "true" ]; then
        log_info "All layer validations passed"
        return 0
    else
        log_error "Some layer validations failed"
        return 1
    fi
}

# Generate reports
generate_reports() {
    local layers="$1"
    local verbose="$2"
    
    for layer in $layers; do
        if ! layer_exists "$layer"; then
            log_error "Layer '$layer' does not exist. Run 'build $layer' first."
            continue
        fi
        
        log_info "Generating report for layer: $layer"
        
        if [ "$verbose" = "true" ]; then
            python3 "$SCRIPT_DIR/layer-utils.py" report --layer "$layer" --verbose
        else
            python3 "$SCRIPT_DIR/layer-utils.py" report --layer "$layer"
        fi
        
        echo ""
    done
}

# Clean layers
clean_layers() {
    local layers="$1"
    
    for layer in $layers; do
        if ! layer_exists "$layer"; then
            log_warn "Layer '$layer' does not exist, skipping clean"
            continue
        fi
        
        local python_dir="$LAYERS_DIR/$layer/python"
        if [ -d "$python_dir" ]; then
            log_info "Cleaning layer: $layer"
            rm -rf "$python_dir"
            log_info "Cleaned layer: $layer"
        else
            log_info "Layer '$layer' already clean"
        fi
    done
}

# Show status
show_status() {
    log_info "Lambda Layer Status"
    echo ""
    
    printf "%-20s %-10s %-15s %-10s\n" "Layer" "Built" "Size (MB)" "Status"
    printf "%-20s %-10s %-15s %-10s\n" "-----" "-----" "---------" "------"
    
    for layer in core-data-science ml-libraries aws-utilities; do
        local built="No"
        local size="0"
        local status="Not Built"
        
        if layer_exists "$layer"; then
            local python_dir="$LAYERS_DIR/$layer/python"
            if [ -d "$python_dir" ]; then
                built="Yes"
                size=$(get_layer_size "$layer")
                
                # Determine status based on size limits
                case "$layer" in
                    "aws-utilities")
                        if [ "$size" -le 50 ]; then
                            status="✓ Valid"
                        else
                            status="✗ Too Large"
                        fi
                        ;;
                    *)
                        if [ "$size" -le 100 ]; then
                            status="✓ Valid"
                        else
                            status="✗ Too Large"
                        fi
                        ;;
                esac
            fi
        fi
        
        printf "%-20s %-10s %-15s %-10s\n" "$layer" "$built" "$size" "$status"
    done
    
    echo ""
}

# Main execution
main() {
    local command="$1"
    local layer_arg="$2"
    local verbose="false"
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                verbose="true"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                if [ -z "$command" ]; then
                    command="$1"
                elif [ -z "$layer_arg" ]; then
                    layer_arg="$1"
                fi
                shift
                ;;
        esac
    done
    
    # Default to 'all' if no layer specified
    if [ -z "$layer_arg" ] && [ "$command" != "status" ]; then
        layer_arg="all"
    fi
    
    # Get layers to process
    local layers
    if [ "$command" != "status" ]; then
        layers=$(get_layers "$layer_arg")
    fi
    
    # Execute command
    case "$command" in
        build)
            build_layers "$layers" "$verbose"
            ;;
        optimize)
            optimize_layers "$layers" "$verbose"
            ;;
        validate)
            validate_layers "$layers" "$verbose"
            ;;
        report)
            generate_reports "$layers" "$verbose"
            ;;
        clean)
            clean_layers "$layers"
            ;;
        status)
            show_status
            ;;
        ""|help)
            show_help
            ;;
        *)
            log_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"