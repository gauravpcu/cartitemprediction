#!/bin/bash

# Build script for Core Data Science Layer
# Optimizes package size and validates constraints

set -e

LAYER_DIR="layers/core-data-science"
PYTHON_DIR="$LAYER_DIR/python"
REQUIREMENTS_FILE="$LAYER_DIR/requirements.txt"
MAX_SIZE_MB=100
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building Core Data Science Layer..."

# Clean previous build
if [ -d "$PYTHON_DIR" ]; then
    echo "Cleaning previous build..."
    rm -rf "$PYTHON_DIR"
fi

# Create python directory for layer
mkdir -p "$PYTHON_DIR"

# Install dependencies
echo "Installing dependencies..."
python3 -m pip install -r "$REQUIREMENTS_FILE" -t "$PYTHON_DIR" --no-deps --no-cache-dir

# Get initial size (macOS compatible)
if command -v gdu >/dev/null 2>&1; then
    INITIAL_SIZE_BYTES=$(gdu -sb "$PYTHON_DIR" | cut -f1)
else
    INITIAL_SIZE_BYTES=$(find "$PYTHON_DIR" -type f -exec stat -f%z {} \; | awk '{sum+=$1} END {print sum}')
fi
INITIAL_SIZE_MB=$((INITIAL_SIZE_BYTES / 1024 / 1024))
echo "Initial size: ${INITIAL_SIZE_MB}MB"

# Optimization using layer utilities
echo "Optimizing package size..."
python3 "$SCRIPT_DIR/layer-utils.py" optimize --layer core-data-science --verbose

# Calculate final size (macOS compatible)
if command -v gdu >/dev/null 2>&1; then
    LAYER_SIZE_BYTES=$(gdu -sb "$PYTHON_DIR" | cut -f1)
else
    LAYER_SIZE_BYTES=$(find "$PYTHON_DIR" -type f -exec stat -f%z {} \; | awk '{sum+=$1} END {print sum}')
fi
LAYER_SIZE_MB=$((LAYER_SIZE_BYTES / 1024 / 1024))
SAVED_MB=$((INITIAL_SIZE_MB - LAYER_SIZE_MB))

echo "Optimization complete:"
echo "  Initial size: ${INITIAL_SIZE_MB}MB"
echo "  Final size: ${LAYER_SIZE_MB}MB"
echo "  Space saved: ${SAVED_MB}MB"

# Validate size constraint
if [ $LAYER_SIZE_MB -gt $MAX_SIZE_MB ]; then
    echo "ERROR: Layer size (${LAYER_SIZE_MB}MB) exceeds maximum allowed size (${MAX_SIZE_MB}MB)"
    exit 1
fi

# Validate imports
echo "Validating imports..."
python3 "$SCRIPT_DIR/layer-utils.py" validate --layer core-data-science

echo "✅ Core Data Science Layer built successfully!"
echo "   Size: ${LAYER_SIZE_MB}MB (under ${MAX_SIZE_MB}MB limit)"
echo "   Location: $PYTHON_DIR"

# Generate detailed report
echo ""
echo "Layer Report:"
python3 "$SCRIPT_DIR/layer-utils.py" report --layer core-data-science

# List main packages for verification
echo ""
echo "Installed packages:"
ls -la "$PYTHON_DIR" | grep "^d" | awk '{print "  - " $9}' | grep -v "^\.$\|^\.\.$"