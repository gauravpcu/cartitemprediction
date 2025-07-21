#!/usr/bin/env python3
"""
Validation script for Task 1.5: Update product lookup table creation
This script validates that the implementation matches the notebook schema and requirements.
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
    """Create comprehensive test data that matches various input formats"""
    
    np.random.seed(42)
    
    customers = [1045, 1046, 1047, 1048]
    facilities = [6420, 6417, 6418, 6419]
    products = [288563, 288564, 288565, 288566, 288567]
    product_names = [
        "Cereal Toasty Os (Cheerios)",
        "Milk Whole Gallon",
        "Bread White Loaf",
        "Eggs Large Dozen",
        "Cheese Cheddar Block"
    ]
    categories = ["Cereal", "Dairy", "Bakery", "Dairy", "Dairy"]
    vendors = ["General Mills", "Dairy Co", "Bakery Inc", "Farm Fresh", "Dairy Co"]
    
    # Generate test data with multiple orders per customer-product combination
    data = []
    base_date = datetime(2024, 1, 1)
    
    for i in range(200):  # More data for better testing
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

def validate_task_1_5():
    """Comprehensive validation of Task 1.5 implementation"""
    
    print("TASK 1.5 VALIDATION: Update product lookup table creation")
    print("=" * 70)
    
    # Test 1: Basic functionality
    print("\n1. Testing basic functionality...")
    df = create_test_data()
    print(f"   Created test dataset with {len(df)} records")
    
    try:
        product_lookup, customer_product_lookup = create_product_lookup_table(df)
        print("   ✅ Function executed successfully")
    except Exception as e:
        print(f"   ❌ Function failed: {e}")
        return False
    
    # Test 2: Schema validation against design document
    print("\n2. Validating schema against design document...")
    
    # Expected schemas from design document
    expected_product_schema = ['ProductID', 'ProductName', 'CategoryName', 'vendorName']
    expected_customer_product_schema = [
        'ProductID', 'ProductName', 'CategoryName', 'vendorName', 
        'CustomerID', 'FacilityID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate'
    ]
    
    product_schema_match = list(product_lookup.columns) == expected_product_schema
    customer_product_schema_match = list(customer_product_lookup.columns) == expected_customer_product_schema
    
    print(f"   Product lookup schema matches design: {product_schema_match}")
    print(f"   Customer-product lookup schema matches design: {customer_product_schema_match}")
    
    if not product_schema_match:
        print(f"     Expected: {expected_product_schema}")
        print(f"     Actual: {list(product_lookup.columns)}")
    
    if not customer_product_schema_match:
        print(f"     Expected: {expected_customer_product_schema}")
        print(f"     Actual: {list(customer_product_lookup.columns)}")
    
    # Test 3: Data quality validation
    print("\n3. Validating data quality...")
    
    data_quality_checks = {
        "No null ProductIDs in product lookup": product_lookup['ProductID'].notna().all(),
        "No null ProductNames in product lookup": product_lookup['ProductName'].notna().all(),
        "No null CategoryNames in product lookup": product_lookup['CategoryName'].notna().all(),
        "No null vendorNames in product lookup": product_lookup['vendorName'].notna().all(),
        "No null CustomerIDs in customer-product lookup": customer_product_lookup['CustomerID'].notna().all(),
        "No null FacilityIDs in customer-product lookup": customer_product_lookup['FacilityID'].notna().all(),
        "OrderCount is positive": (customer_product_lookup['OrderCount'] > 0).all(),
        "FirstOrderDate is datetime": pd.api.types.is_datetime64_any_dtype(customer_product_lookup['FirstOrderDate']),
        "LastOrderDate is datetime": pd.api.types.is_datetime64_any_dtype(customer_product_lookup['LastOrderDate']),
        "FirstOrderDate <= LastOrderDate": (customer_product_lookup['FirstOrderDate'] <= customer_product_lookup['LastOrderDate']).all()
    }
    
    all_quality_checks_pass = True
    for check_name, result in data_quality_checks.items():
        print(f"   {check_name}: {'✅' if result else '❌'}")
        if not result:
            all_quality_checks_pass = False
    
    # Test 4: Customer-product relationship validation
    print("\n4. Validating customer-product relationships...")
    
    # Check that we have the right number of unique combinations
    unique_combinations_in_data = df[['CustomerID', 'FacilityID', 'ProductID']].drop_duplicates()
    expected_relationships = len(unique_combinations_in_data)
    actual_relationships = len(customer_product_lookup)
    
    relationships_match = expected_relationships == actual_relationships
    print(f"   Expected {expected_relationships} relationships, got {actual_relationships}: {'✅' if relationships_match else '❌'}")
    
    # Test 5: Notebook schema compliance
    print("\n5. Validating notebook schema compliance...")
    
    # Check that the schema exactly matches what's specified in the design document
    notebook_compliance_checks = {
        "Product lookup has exactly 4 columns": len(product_lookup.columns) == 4,
        "Customer-product lookup has exactly 9 columns": len(customer_product_lookup.columns) == 9,
        "Product lookup column order matches design": list(product_lookup.columns) == expected_product_schema,
        "Customer-product lookup column order matches design": list(customer_product_lookup.columns) == expected_customer_product_schema,
        "vendorName uses lowercase 'v' (not VendorName)": 'vendorName' in product_lookup.columns and 'vendorName' in customer_product_lookup.columns
    }
    
    all_compliance_checks_pass = True
    for check_name, result in notebook_compliance_checks.items():
        print(f"   {check_name}: {'✅' if result else '❌'}")
        if not result:
            all_compliance_checks_pass = False
    
    # Test 6: Edge case handling
    print("\n6. Testing edge case handling...")
    
    # Test with missing columns
    df_minimal = df[['CustomerID', 'FacilityID', 'ProductID', 'CreateDate']].copy()
    try:
        product_lookup_minimal, customer_product_lookup_minimal = create_product_lookup_table(df_minimal)
        
        # Should have default values
        has_default_names = (product_lookup_minimal['ProductName'].str.startswith('Product')).all()
        has_default_categories = (product_lookup_minimal['CategoryName'] == 'General').all()
        has_default_vendors = (product_lookup_minimal['vendorName'].str.startswith('Vendor')).all()
        
        print(f"   Handles missing ProductName with defaults: {'✅' if has_default_names else '❌'}")
        print(f"   Handles missing CategoryName with defaults: {'✅' if has_default_categories else '❌'}")
        print(f"   Handles missing vendorName with defaults: {'✅' if has_default_vendors else '❌'}")
        
        edge_case_pass = has_default_names and has_default_categories and has_default_vendors
    except Exception as e:
        print(f"   ❌ Edge case handling failed: {e}")
        edge_case_pass = False
    
    # Final assessment
    print("\n" + "=" * 70)
    print("FINAL ASSESSMENT:")
    
    all_tests_pass = (
        product_schema_match and 
        customer_product_schema_match and 
        all_quality_checks_pass and 
        relationships_match and 
        all_compliance_checks_pass and 
        edge_case_pass
    )
    
    if all_tests_pass:
        print("✅ ALL TESTS PASSED - Task 1.5 implementation is correct!")
        print("\nImplementation successfully:")
        print("- Creates product lookup table matching notebook schema")
        print("- Generates customer-product relationship data")
        print("- Handles various input column name variations")
        print("- Provides appropriate default values for missing data")
        print("- Maintains proper data types and relationships")
        print("- Ready for S3 and DynamoDB storage")
    else:
        print("❌ SOME TESTS FAILED - Please review the implementation")
    
    return all_tests_pass

if __name__ == "__main__":
    success = validate_task_1_5()
    exit(0 if success else 1)