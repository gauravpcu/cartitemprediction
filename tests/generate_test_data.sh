#!/bin/bash

# Generate sample test data for the optimized Lambda deployment

echo "🔧 Generating Test Data for Optimized Lambda Deployment"
echo "====================================================="

# Ask for number of rows
read -p "📊 How many rows of data to generate? (default: 1000): " NUM_ROWS
NUM_ROWS=${NUM_ROWS:-1000}

# Generate filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="test_data_${TIMESTAMP}.csv"

echo "📁 Generating $NUM_ROWS rows of data..."
echo "💾 Output file: $OUTPUT_FILE"

# Create CSV header
echo "CreateDate,CustomerID,FacilityID,ProductID,Quantity,UnitPrice,ProductCategory,ProductDescription" > "$OUTPUT_FILE"

# Generate data
for i in $(seq 1 $NUM_ROWS); do
    # Random date in the last year
    DAYS_AGO=$((RANDOM % 365))
    DATE=$(date -v-${DAYS_AGO}d +%Y-%m-%d 2>/dev/null || date -d "$DAYS_AGO days ago" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
    
    # Random customer (1-20)
    CUSTOMER_ID="CUST$(printf "%03d" $((RANDOM % 20 + 1)))"
    
    # Random facility (1-10)
    FACILITY_ID="FAC$(printf "%03d" $((RANDOM % 10 + 1)))"
    
    # Random product (1-100)
    PRODUCT_ID="PROD$(printf "%04d" $((RANDOM % 100 + 1)))"
    
    # Random quantity (1-500)
    QUANTITY=$((RANDOM % 500 + 1))
    
    # Random unit price (5.00-100.00)
    UNIT_PRICE=$(echo "scale=2; ($RANDOM % 9500 + 500) / 100" | bc 2>/dev/null || echo "25.50")
    
    # Random category
    CATEGORIES=("Electronics" "Office Supplies" "Industrial" "Food & Beverage" "Healthcare")
    CATEGORY=${CATEGORIES[$((RANDOM % 5))]}
    
    # Product description
    DESCRIPTION="Product $PRODUCT_ID Description"
    
    # Write row
    echo "$DATE,$CUSTOMER_ID,$FACILITY_ID,$PRODUCT_ID,$QUANTITY,$UNIT_PRICE,$CATEGORY,$DESCRIPTION" >> "$OUTPUT_FILE"
    
    # Progress indicator
    if [ $((i % 100)) -eq 0 ]; then
        echo "📈 Generated $i/$NUM_ROWS rows..."
    fi
done

echo "✅ Generated $NUM_ROWS rows of test data"
echo "📁 File: $OUTPUT_FILE"
echo "📊 File size: $(ls -lh "$OUTPUT_FILE" | awk '{print $5}')"

# Show preview
echo ""
echo "📋 Data preview:"
head -n 6 "$OUTPUT_FILE"
echo "..."
echo "$(tail -n 1 "$OUTPUT_FILE")"

echo ""
echo "🚀 Ready to upload! Run:"
echo "   ./upload_new_file.sh $OUTPUT_FILE"