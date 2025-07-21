#!/bin/bash

# Comprehensive validation script for Core Data Science Layer
# Tests build, optimization, size constraints, and functionality

set -e

LAYER_DIR="layers/core-data-science"
PYTHON_DIR="$LAYER_DIR/python"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔍 Comprehensive Core Data Science Layer Validation"
echo "=================================================="

# Check if layer exists
if [ ! -d "$PYTHON_DIR" ]; then
    echo "❌ Layer not found. Building layer first..."
    ./scripts/build-core-data-science-layer.sh
fi

echo ""
echo "1. Size Validation"
echo "------------------"
python3 "$SCRIPT_DIR/layer-utils.py" validate --layer core-data-science

echo ""
echo "2. Import Validation"
echo "-------------------"
echo "Testing imports directly..."
python3 -c "
import sys
sys.path.insert(0, '$PYTHON_DIR')
try:
    import pandas as pd
    print('✅ pandas import successful - version:', pd.__version__)
    import numpy as np
    print('✅ numpy import successful - version:', np.__version__)
    from dateutil import parser
    print('✅ python-dateutil import successful')
    print('✅ All imports validated successfully')
except ImportError as e:
    print('❌ Import failed:', e)
    sys.exit(1)
"

echo ""
echo "3. Functionality Tests"
echo "---------------------"
python3 tests/test_core_data_science_layer.py

echo ""
echo "4. Layer Report"
echo "--------------"
python3 "$SCRIPT_DIR/layer-utils.py" report --layer core-data-science

echo ""
echo "✅ All validations passed!"
echo "Core Data Science Layer is ready for deployment."