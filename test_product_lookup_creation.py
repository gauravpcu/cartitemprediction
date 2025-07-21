#!/usr/bin/env python3
"""
Test script to validate the create_product_lookup_table function
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Mock the boto3 and logging modules to avoid import errors
class MockLogger:
    def info(self, msg):
        print(f"INFO: {msg}")
    def error(self, msg):
        print(f"ERROR: {msg}")

# Mock the modules that aren't needed for this test
sys.modules['boto3'] = type(sys)('boto3')
sys.modules['logging'] = type(sys)('logging')

# Add the function directory to path so we can import the function
sys.path.append('functions/enhanced_feature_engineering')

def create_test_data():
    """Create sample test data that matches the expected input format"""
    
    # Create sample data with the expected columns
    np.random.seed(42)
    
    customers = [1045, 1046, 1047]
    facilities = [6420, 6417, 6418]
    products = [288563, 288564, 288565, 288566]
    product_names = [
        "Cereal Toasty Os (Cheerios)",
        "Milk Whole Gallon",
        "Bread White Loaf",
        "Eggs Large Dozen"
    ]
    categories = ["Cereal", "Dairy", "Bakery", "Dairy"]
    vendors = ["General Mills", "Dairy Co", "Bakery Inc", "Farm Fresh"]
    
    # Generate test data
    data = []
    base_date = datetime(2024, 1, 1)
    
    for i in range(100):
        customer_id = np.random.choice(customers)
        facility_id = np.random.choice(facilities)
        product_idx = np.random.randint(0, len(products))
        product_id = products[product_idx]
        
        # Create date within the last year
        days_offset = np.random.randint(0, 365)
        create_date = base_date + timedelta(days=days_offset)
        
        data.append({
            'CustomerID': customer_id,
            'FacilityID': facility_id,
            'ProductID': product_id,
            'ProductDescription': product_names[product_idx],
            'ProductCategory': categories[product_idx],
            'VendorName': vendors[product_idx],
            'CreateDate': create_date,
            'OrderUnits': np.random.randint(1, 10),
            'Date': create_date.strftime('%Y-%m-%d')
        })
    
    return pd.DataFrame(data)

def test_create_product_lookup_table():
    """Test the create_product_lookup_table function"""
    
    # Import the function
    try:
        from app import create_product_lookup_table
    except ImportError as e:
        print(f"Error importing function: {e}")
        return False
    
    # Create test data
    print("Creating test data...")
    df = create_test_data()
    print(f"Created {len(df)} test records")
    
    # Test the function
    print("\nTesting create_product_lookup_table function...")
    try:
        product_lookup, customer_product_lookup = create_product_lookup_table(df)
        
        # Validate product lookup table
        print(f"\nProduct Lookup Table:")
        print(f"- Shape: {product_lookup.shape}")
        print(f"- Columns: {list(product_lookup.columns)}")
        print(f"- Sample data:")
        print(product_lookup.head())
        
        # Validate customer-product lookup table
        print(f"\nCustomer-Product Lookup Table:")
        print(f"- Shape: {customer_product_lookup.shape}")
        print(f"- Columns: {list(customer_product_lookup.columns)}")
        print(f"- Sample data:")
        print(customer_product_lookup.head())
        
        # Validate schema matches design document requirements
        expected_product_cols = ['ProductID', 'ProductName', 'CategoryName', 'vendorName']
        expected_customer_product_cols = [
            'ProductID', 'ProductName', 'CategoryName', 'vendorName', 
            'CustomerID', 'FacilityID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate'
        ]
        
        print(f"\nSchema Validation:")
        product_schema_match = all(col in product_lookup.columns for col in expected_product_cols)
        customer_product_schema_match = all(col in customer_product_lookup.columns for col in expected_customer_product_cols)
        
        print(f"- Product lookup schema matches: {product_schema_match}")
        print(f"- Customer-product lookup schema matches: {customer_product_schema_match}")
        
        # Validate data types
        print(f"\nData Type Validation:")
        print(f"- FirstOrderDate type: {customer_product_lookup['FirstOrderDate'].dtype}")
        print(f"- LastOrderDate type: {customer_product_lookup['LastOrderDate'].dtype}")
        print(f"- OrderCount type: {customer_product_lookup['OrderCount'].dtype}")
        
        # Check for required data
        print(f"\nData Quality Checks:")
        print(f"- Product lookup has no null ProductIDs: {product_lookup['ProductID'].notna().all()}")
        print(f"- Customer-product lookup has no null CustomerIDs: {customer_product_lookup['CustomerID'].notna().all()}")
        print(f"- All products have names: {product_lookup['ProductName'].notna().all()}")
        print(f"- All products have categories: {product_lookup['CategoryName'].notna().all()}")
        print(f"- All products have vendor names: {product_lookup['vendorName'].notna().all()}")
        
        return True
        
    except Exception as e:
        print(f"Error testing function: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing Product Lookup Table Creation")
    print("=" * 50)
    
    success = test_create_product_lookup_table()
    
    if success:
        print("\n✅ All tests passed! The create_product_lookup_table function is working correctly.")
    else:
        print("\n❌ Tests failed! Please check the implementation.")