#!/bin/bash

# Build script for ML Libraries Layer
# Optimizes package size and validates constraints

set -e

LAYER_DIR="layers/ml-libraries"
PYTHON_DIR="$LAYER_DIR/python"
REQUIREMENTS_FILE="$LAYER_DIR/requirements.txt"
MAX_SIZE_MB=105
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building ML Libraries Layer..."

# Clean previous build
if [ -d "$PYTHON_DIR" ]; then
    echo "Cleaning previous build..."
    rm -rf "$PYTHON_DIR"
fi

# Create python directory for layer
mkdir -p "$PYTHON_DIR"

# Copy from existing AWS SAM build instead of building from scratch
echo "Copying ML libraries from existing AWS SAM build..."
SOURCE_DIR=".aws-sam/deps/88daedff-2a99-4fe8-bd06-c272def008ff"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "ERROR: Source directory not found. Please run 'sam build' first."
    exit 1
fi

# Copy ML-specific packages
echo "Copying scikit-learn..."
cp -r "$SOURCE_DIR/sklearn" "$PYTHON_DIR/"
cp -r "$SOURCE_DIR/scikit_learn-1.6.1.dist-info" "$PYTHON_DIR/"
cp -r "$SOURCE_DIR/scikit_learn.libs" "$PYTHON_DIR/"

echo "Copying scipy..."
cp -r "$SOURCE_DIR/scipy" "$PYTHON_DIR/"
cp -r "$SOURCE_DIR/scipy-1.13.1.dist-info" "$PYTHON_DIR/"
cp -r "$SOURCE_DIR/scipy.libs" "$PYTHON_DIR/"

echo "Copying joblib..."
cp -r "$SOURCE_DIR/joblib" "$PYTHON_DIR/"
cp -r "$SOURCE_DIR/joblib-1.5.1.dist-info" "$PYTHON_DIR/"

echo "Copying threadpoolctl..."
cp "$SOURCE_DIR/threadpoolctl.py" "$PYTHON_DIR/"
cp -r "$SOURCE_DIR/threadpoolctl-3.6.0.dist-info" "$PYTHON_DIR/"

echo "ML libraries copied successfully"

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
python3 "$SCRIPT_DIR/layer-utils.py" optimize --layer ml-libraries --verbose

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
python3 "$SCRIPT_DIR/layer-utils.py" validate --layer ml-libraries

echo "✅ ML Libraries Layer built successfully!"
echo "   Size: ${LAYER_SIZE_MB}MB (under ${MAX_SIZE_MB}MB limit)"
echo "   Location: $PYTHON_DIR"

# Generate detailed report
echo ""
echo "Layer Report:"
python3 "$SCRIPT_DIR/layer-utils.py" report --layer ml-libraries

# List main packages for verification
echo ""
echo "Installed packages:"
ls -la "$PYTHON_DIR" | grep "^d" | awk '{print "  - " $9}' | grep -v "^\.$\|^\.\.$"