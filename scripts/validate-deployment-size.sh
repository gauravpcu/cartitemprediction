#!/bin/bash
#
# Deployment Size Validation Script
# Prevents deployment of oversized Lambda functions and layers
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${YELLOW}Lambda Deployment Size Validation${NC}"
echo "=================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed${NC}"
    exit 1
fi

# Run size validation
echo "Validating Lambda function and layer sizes..."
echo ""

# Create reports directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/reports"

# Run validation and save detailed report
REPORT_FILE="$PROJECT_ROOT/reports/size-validation-$(date +%Y%m%d-%H%M%S).json"
TEXT_REPORT_FILE="$PROJECT_ROOT/reports/size-validation-$(date +%Y%m%d-%H%M%S).txt"

if python3 "$SCRIPT_DIR/size-validation.py" check --workspace "$PROJECT_ROOT" --output "$REPORT_FILE" --verbose; then
    echo ""
    echo -e "${GREEN}✓ Size validation passed - deployment can proceed${NC}"
    
    # Also generate text report for easy reading
    python3 "$SCRIPT_DIR/size-validation.py" report --workspace "$PROJECT_ROOT" --format text --output "$TEXT_REPORT_FILE"
    
    echo "Detailed reports saved:"
    echo "  JSON: $REPORT_FILE"
    echo "  Text: $TEXT_REPORT_FILE"
    
    exit 0
else
    echo ""
    echo -e "${RED}✗ Size validation failed - deployment blocked${NC}"
    echo ""
    echo "To fix size issues:"
    echo "1. Run layer optimization: ./scripts/build-layers.sh"
    echo "2. Remove unnecessary dependencies from function requirements.txt"
    echo "3. Check the detailed report for largest files to remove"
    
    # Generate text report for troubleshooting
    python3 "$SCRIPT_DIR/size-validation.py" report --workspace "$PROJECT_ROOT" --format text --output "$TEXT_REPORT_FILE" || true
    
    echo ""
    echo "Detailed report saved to: $TEXT_REPORT_FILE"
    
    exit 1
fi