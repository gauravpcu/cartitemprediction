#!/usr/bin/env python3
"""
Standalone test script to validate the create_product_lookup_table function
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_product_lookup_table(df):
    """Create a lookup table for product information matching notebook schema"""
    print("INFO: Creating product lookup table...")
    
    # Handle different column names for product information
    product_cols = ['ProductID']
    product_name_col = None
    category_name_col = None
    vendor_name_col = None
    
    if 'ProductDescription' in df.columns:
        product_cols.append('ProductDescription')
        product_name_col = 'ProductDescription'
    elif 'ProductName' in df.columns:
        product_cols.append('ProductName')
        product_name_col = 'ProductName'
    
    if 'ProductCategory' in df.columns:
        product_cols.append('ProductCategory')
        category_name_col = 'ProductCategory'
    elif 'CategoryName' in df.columns:
        product_cols.append('CategoryName')
        category_name_col = 'CategoryName'
    
    if 'VendorName' in df.columns:
        product_cols.append('VendorName')
        vendor_name_col = 'VendorName'
    
    # Create basic product lookup with standardized column names
    product_lookup = df[product_cols].drop_duplicates()
    
    # Standardize column names to match notebook schema
    rename_dict = {'ProductID': 'ProductID'}
    if product_name_col:
        rename_dict[product_name_col] = 'ProductName'
    if category_name_col:
        rename_dict[category_name_col] = 'CategoryName'
    if vendor_name_col:
        rename_dict[vendor_name_col] = 'vendorName'
    
    product_lookup = product_lookup.rename(columns=rename_dict)
    
    # Add missing columns with default values if not present
    if 'ProductName' not in product_lookup.columns:
        product_lookup['ProductName'] = 'Product ' + product_lookup['ProductID'].astype(str)
    if 'CategoryName' not in product_lookup.columns:
        product_lookup['CategoryName'] = 'General'
    if 'vendorName' not in product_lookup.columns:
        product_lookup['vendorName'] = 'Vendor' + product_lookup['ProductID'].astype(str).str.replace('PROD', '')
    
    # Create customer-product relationships matching notebook schema
    # Use OrderUnits if available, otherwise count occurrences
    if 'OrderUnits' in df.columns:
        customer_products = df.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg({
            'OrderUnits': 'count',  # Number of order lines
            'CreateDate': ['min', 'max']  # First and last order dates
        }).reset_index()
        customer_products.columns = ['CustomerID', 'FacilityID', 'ProductID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate']
    else:
        customer_products = df.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg({
            'CreateDate': ['count', 'min', 'max']  # Count, first and last order dates
        }).reset_index()
        customer_products.columns = ['CustomerID', 'FacilityID', 'ProductID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate']
    
    # Merge with product info to create customer-product lookup matching notebook schema
    customer_product_lookup = customer_products.merge(product_lookup, on='ProductID', how='left')
    
    # Ensure proper data types for dates
    customer_product_lookup['FirstOrderDate'] = pd.to_datetime(customer_product_lookup['FirstOrderDate'])
    customer_product_lookup['LastOrderDate'] = pd.to_datetime(customer_product_lookup['LastOrderDate'])
    
    # Reorder columns to match notebook schema exactly
    # Schema: ProductID, ProductName, CategoryName, vendorName, CustomerID, FacilityID, OrderCount, FirstOrderDate, LastOrderDate
    customer_product_lookup = customer_product_lookup[[
        'ProductID', 'ProductName', 'CategoryName', 'vendorName', 
        'CustomerID', 'FacilityID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate'
    ]]
    
    print(f"INFO: Created product lookup with {len(product_lookup)} unique products")
    print(f"INFO: Created customer-product lookup with {len(customer_product_lookup)} relationships")
    
    return product_lookup, customer_product_lookup

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
        
        # Validate that the schema exactly matches the design document
        print(f"\nExact Schema Validation:")
        product_cols_exact = list(product_lookup.columns) == expected_product_cols
        customer_product_cols_exact = list(customer_product_lookup.columns) == expected_customer_product_cols
        
        print(f"- Product lookup columns exact match: {product_cols_exact}")
        print(f"- Customer-product lookup columns exact match: {customer_product_cols_exact}")
        
        if not product_cols_exact:
            print(f"  Expected: {expected_product_cols}")
            print(f"  Actual: {list(product_lookup.columns)}")
        
        if not customer_product_cols_exact:
            print(f"  Expected: {expected_customer_product_cols}")
            print(f"  Actual: {list(customer_product_lookup.columns)}")
        
        return product_schema_match and customer_product_schema_match
        
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