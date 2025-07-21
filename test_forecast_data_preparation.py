#!/usr/bin/env python3
"""
Test script to validate the forecast data preparation functions
match the notebook's SageMaker DeepAR format requirements.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Define the functions locally for testing (copied from the Lambda function)
def get_us_holidays(year):
    """Get US federal holidays for a given year with proper date calculations"""
    holidays = {}
    
    # Fixed date holidays
    holidays[f'{year}-01-01'] = "New Year's Day"
    holidays[f'{year}-06-19'] = "Juneteenth"
    holidays[f'{year}-07-04'] = "Independence Day"
    holidays[f'{year}-11-11'] = "Veterans Day"
    holidays[f'{year}-12-25'] = "Christmas Day"
    
    # Calculate variable date holidays
    # Martin Luther King Jr. Day - 3rd Monday in January
    from datetime import date
    jan_1 = date(year, 1, 1)
    days_to_first_monday = (7 - jan_1.weekday()) % 7
    first_monday_jan = jan_1 + pd.Timedelta(days=days_to_first_monday)
    mlk_day = first_monday_jan + pd.Timedelta(days=14)  # 3rd Monday
    holidays[mlk_day.strftime('%Y-%m-%d')] = "Martin Luther King Jr. Day"
    
    # Presidents' Day - 3rd Monday in February
    feb_1 = date(year, 2, 1)
    days_to_first_monday = (7 - feb_1.weekday()) % 7
    first_monday_feb = feb_1 + pd.Timedelta(days=days_to_first_monday)
    presidents_day = first_monday_feb + pd.Timedelta(days=14)  # 3rd Monday
    holidays[presidents_day.strftime('%Y-%m-%d')] = "Presidents' Day"
    
    # Memorial Day - Last Monday in May
    may_31 = date(year, 5, 31)
    weekday = may_31.weekday()  # 0=Monday, 1=Tuesday, ..., 6=Sunday
    if weekday == 0:  # Already Monday
        days_back = 0
    else:
        days_back = weekday
    memorial_day = may_31 - pd.Timedelta(days=days_back)
    holidays[memorial_day.strftime('%Y-%m-%d')] = "Memorial Day"
    
    # Labor Day - 1st Monday in September
    sep_1 = date(year, 9, 1)
    days_to_first_monday = (7 - sep_1.weekday()) % 7
    labor_day = sep_1 + pd.Timedelta(days=days_to_first_monday)
    holidays[labor_day.strftime('%Y-%m-%d')] = "Labor Day"
    
    # Columbus Day - 2nd Monday in October
    oct_1 = date(year, 10, 1)
    days_to_first_monday = (7 - oct_1.weekday()) % 7
    first_monday_oct = oct_1 + pd.Timedelta(days=days_to_first_monday)
    columbus_day = first_monday_oct + pd.Timedelta(days=7)  # 2nd Monday
    holidays[columbus_day.strftime('%Y-%m-%d')] = "Columbus Day"
    
    # Thanksgiving Day - 4th Thursday in November
    nov_1 = date(year, 11, 1)
    days_to_first_thursday = (3 - nov_1.weekday()) % 7
    first_thursday_nov = nov_1 + pd.Timedelta(days=days_to_first_thursday)
    thanksgiving_day = first_thursday_nov + pd.Timedelta(days=21)  # 4th Thursday
    holidays[thanksgiving_day.strftime('%Y-%m-%d')] = "Thanksgiving Day"
    
    return holidays

def extract_temporal_features(df):
    """Extract time-based features from the CreateDate"""
    print("Extracting temporal features...")
    
    # Convert date strings to datetime objects if needed
    if df['CreateDate'].dtype == 'object':
        df['CreateDate'] = pd.to_datetime(df['CreateDate'])
    
    # Basic date components
    df['OrderYear'] = df['CreateDate'].dt.year
    df['OrderMonth'] = df['CreateDate'].dt.month
    df['OrderDay'] = df['CreateDate'].dt.day
    df['OrderDayOfWeek'] = df['CreateDate'].dt.dayofweek  # Monday=0, Sunday=6
    df['OrderHour'] = df['CreateDate'].dt.hour
    
    # Cyclical encoding of time features - matching notebook implementation exactly
    df['DayOfWeek_sin'] = np.sin(df['OrderDayOfWeek'] * (2 * np.pi / 7))
    df['DayOfWeek_cos'] = np.cos(df['OrderDayOfWeek'] * (2 * np.pi / 7))
    
    df['DayOfMonth_sin'] = np.sin((df['OrderDay'] - 1) * (2 * np.pi / 31))
    df['DayOfMonth_cos'] = np.cos((df['OrderDay'] - 1) * (2 * np.pi / 31))
    
    df['MonthOfYear_sin'] = np.sin((df['OrderMonth'] - 1) * (2 * np.pi / 12))
    df['MonthOfYear_cos'] = np.cos((df['OrderMonth'] - 1) * (2 * np.pi / 12))
    
    # Quarter - matching notebook implementation exactly
    df['OrderQuarter'] = df['OrderMonth'].apply(lambda x: (x-1)//3 + 1)
    
    # Is weekend - matching notebook implementation exactly
    df['IsWeekend'] = df['OrderDayOfWeek'].apply(lambda x: 1 if x >= 5 else 0)
    
    # Get dynamic US holidays for the years present in the data
    years_in_data = df['OrderYear'].unique()
    all_holidays = {}
    for year in years_in_data:
        year_holidays = get_us_holidays(year)
        all_holidays.update(year_holidays)
    
    df['Date'] = df['CreateDate'].dt.strftime('%Y-%m-%d')
    df['IsHoliday'] = df['Date'].apply(lambda x: 1 if x in all_holidays else 0)
    df['HolidayName'] = df['Date'].apply(lambda x: all_holidays.get(x, ''))
    
    return df

def prepare_product_forecast_data(df):
    """Prepare data for product-level forecasting in SageMaker DeepAR format"""
    print("Preparing product-level forecast data...")
    
    # Group by customer, facility, product, and date to get daily quantities
    if 'OrderUnits' in df.columns:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date'])['OrderUnits'].sum().reset_index(name='Quantity')
    else:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information - handle different column names
    product_cols = ['ProductID']
    if 'ProductDescription' in df.columns:
        product_cols.append('ProductDescription')
    elif 'ProductName' in df.columns:
        product_cols.append('ProductName')
    
    if 'ProductCategory' in df.columns:
        product_cols.append('ProductCategory')
    elif 'CategoryName' in df.columns:
        product_cols.append('CategoryName')
    
    if 'VendorName' in df.columns:
        product_cols.append('VendorName')
    
    product_info = df[product_cols].drop_duplicates()
    product_daily = product_daily.merge(product_info, on='ProductID', how='left')
    
    # Create item_id that includes customer, facility, and product for unique identification
    forecast_df = pd.DataFrame({
        'item_id': (product_daily['CustomerID'].astype(str) + '_' + 
                   product_daily['FacilityID'].astype(str) + '_' + 
                   product_daily['ProductID'].astype(str)),
        'timestamp': pd.to_datetime(product_daily['Date']),
        'target_value': product_daily['Quantity'],
        'customer_id': product_daily['CustomerID'],
        'facility_id': product_daily['FacilityID'],
        'product_id': product_daily['ProductID']
    })
    
    # Add product metadata
    if 'ProductDescription' in product_daily.columns:
        forecast_df['product_name'] = product_daily['ProductDescription']
    elif 'ProductName' in product_daily.columns:
        forecast_df['product_name'] = product_daily['ProductName']
    else:
        forecast_df['product_name'] = 'Product ' + forecast_df['product_id'].astype(str)
    
    if 'ProductCategory' in product_daily.columns:
        forecast_df['category_name'] = product_daily['ProductCategory']
    elif 'CategoryName' in product_daily.columns:
        forecast_df['category_name'] = product_daily['CategoryName']
    else:
        forecast_df['category_name'] = 'General'
    
    if 'VendorName' in product_daily.columns:
        forecast_df['vendor_name'] = product_daily['VendorName']
    else:
        forecast_df['vendor_name'] = 'Vendor' + forecast_df['product_id'].astype(str).str.replace('PROD', '')
    
    # Add temporal features required for SageMaker DeepAR (matching notebook implementation)
    forecast_df['day_of_week'] = forecast_df['timestamp'].dt.dayofweek
    forecast_df['month'] = forecast_df['timestamp'].dt.month
    
    # Sort by item_id and timestamp for proper time series format
    forecast_df = forecast_df.sort_values(['item_id', 'timestamp']).reset_index(drop=True)
    
    return forecast_df

def prepare_customer_level_forecast_data(df):
    """Prepare data for customer-level forecasting (aggregated forecasts)"""
    print("Preparing customer-level forecast data...")
    
    # Group by customer, facility, and date for total order count
    if 'OrderUnits' in df.columns:
        customer_daily = df.groupby(['CustomerID', 'FacilityID', 'Date'])['OrderUnits'].sum().reset_index(name='TotalUnits')
    else:
        customer_daily = df.groupby(['CustomerID', 'FacilityID', 'Date']).size().reset_index(name='TotalItems')
    
    # Also calculate unique products ordered per day
    unique_products_daily = df.groupby(['CustomerID', 'FacilityID', 'Date'])['ProductID'].nunique().reset_index(name='UniqueProducts')
    
    # Calculate total order value if Price column exists
    if 'Price' in df.columns:
        if 'OrderUnits' in df.columns:
            df['OrderValue'] = df['OrderUnits'] * df['Price']
        else:
            df['OrderValue'] = df['Price']
        order_value_daily = df.groupby(['CustomerID', 'FacilityID', 'Date'])['OrderValue'].sum().reset_index(name='TotalValue')
        customer_daily = customer_daily.merge(order_value_daily, on=['CustomerID', 'FacilityID', 'Date'])
    
    # Merge the data
    customer_daily = customer_daily.merge(unique_products_daily, on=['CustomerID', 'FacilityID', 'Date'])
    
    # Create forecast format for total items/units
    if 'TotalUnits' in customer_daily.columns:
        forecast_df_items = pd.DataFrame({
            'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                       customer_daily['FacilityID'].astype(str) + '_TOTAL_UNITS'),
            'timestamp': pd.to_datetime(customer_daily['Date']),
            'target_value': customer_daily['TotalUnits'],
            'customer_id': customer_daily['CustomerID'],
            'facility_id': customer_daily['FacilityID'],
            'metric_type': 'TOTAL_UNITS'
        })
    else:
        forecast_df_items = pd.DataFrame({
            'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                       customer_daily['FacilityID'].astype(str) + '_TOTAL_ITEMS'),
            'timestamp': pd.to_datetime(customer_daily['Date']),
            'target_value': customer_daily['TotalItems'],
            'customer_id': customer_daily['CustomerID'],
            'facility_id': customer_daily['FacilityID'],
            'metric_type': 'TOTAL_ITEMS'
        })
    
    # Create forecast format for unique products
    forecast_df_products = pd.DataFrame({
        'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                   customer_daily['FacilityID'].astype(str) + '_UNIQUE_PRODUCTS'),
        'timestamp': pd.to_datetime(customer_daily['Date']),
        'target_value': customer_daily['UniqueProducts'],
        'customer_id': customer_daily['CustomerID'],
        'facility_id': customer_daily['FacilityID'],
        'metric_type': 'UNIQUE_PRODUCTS'
    })
    
    # Create forecast format for total value if available
    forecast_dfs = [forecast_df_items, forecast_df_products]
    if 'TotalValue' in customer_daily.columns:
        forecast_df_value = pd.DataFrame({
            'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                       customer_daily['FacilityID'].astype(str) + '_TOTAL_VALUE'),
            'timestamp': pd.to_datetime(customer_daily['Date']),
            'target_value': customer_daily['TotalValue'],
            'customer_id': customer_daily['CustomerID'],
            'facility_id': customer_daily['FacilityID'],
            'metric_type': 'TOTAL_VALUE'
        })
        forecast_dfs.append(forecast_df_value)
    
    # Combine all datasets
    forecast_df = pd.concat(forecast_dfs, ignore_index=True)
    
    # Add temporal features required for SageMaker DeepAR (matching notebook implementation)
    forecast_df['day_of_week'] = forecast_df['timestamp'].dt.dayofweek
    forecast_df['month'] = forecast_df['timestamp'].dt.month
    
    # Sort by item_id and timestamp for proper time series format
    forecast_df = forecast_df.sort_values(['item_id', 'timestamp']).reset_index(drop=True)
    
    return forecast_df

def create_sample_data():
    """Create sample data that matches the expected input format"""
    # Create sample data with multiple customers, facilities, and products
    np.random.seed(42)
    
    customers = ['CUST001', 'CUST002', 'CUST003']
    facilities = ['FAC001', 'FAC002']
    products = ['PROD001', 'PROD002', 'PROD003', 'PROD004']
    
    # Generate date range
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    
    data = []
    for customer in customers:
        for facility in facilities:
            for product in products:
                # Generate some orders for this combination (not every day)
                num_orders = np.random.randint(50, 150)  # Random number of orders
                order_dates = np.random.choice(date_range, size=num_orders, replace=False)
                
                for order_date in order_dates:
                    data.append({
                        'CustomerID': customer,
                        'FacilityID': facility,
                        'ProductID': product,
                        'ProductDescription': f'Product {product}',
                        'ProductCategory': f'Category {product[-1]}',
                        'VendorName': f'Vendor {product[-1]}',
                        'CreateDate': order_date,
                        'OrderUnits': np.random.randint(1, 10),
                        'Price': np.random.uniform(10, 100)
                    })
    
    df = pd.DataFrame(data)
    df['CreateDate'] = pd.to_datetime(df['CreateDate'])
    return df

def test_prepare_product_forecast_data():
    """Test the prepare_product_forecast_data function"""
    print("Testing prepare_product_forecast_data function...")
    
    # Create sample data
    df = create_sample_data()
    
    # Add temporal features (required by the function)
    df = extract_temporal_features(df)
    
    # Test the function
    forecast_df = prepare_product_forecast_data(df)
    
    # Validate the output
    print(f"Input data shape: {df.shape}")
    print(f"Forecast data shape: {forecast_df.shape}")
    print(f"Columns: {list(forecast_df.columns)}")
    
    # Check required columns for SageMaker DeepAR format
    required_columns = [
        'item_id', 'timestamp', 'target_value', 'customer_id', 
        'facility_id', 'product_id', 'product_name', 'category_name',
        'day_of_week', 'month'  # Temporal features for DeepAR
    ]
    
    missing_columns = [col for col in required_columns if col not in forecast_df.columns]
    if missing_columns:
        print(f"❌ Missing required columns: {missing_columns}")
        return False
    else:
        print("✅ All required columns present")
    
    # Check data types
    assert forecast_df['timestamp'].dtype == 'datetime64[ns]', "timestamp should be datetime"
    assert forecast_df['target_value'].dtype in ['int64', 'float64', 'int32'], "target_value should be numeric"
    assert forecast_df['day_of_week'].dtype in ['int64', 'int32'], "day_of_week should be integer"
    assert forecast_df['month'].dtype in ['int64', 'int32'], "month should be integer"
    
    # Check value ranges
    assert forecast_df['day_of_week'].min() >= 0 and forecast_df['day_of_week'].max() <= 6, "day_of_week should be 0-6"
    assert forecast_df['month'].min() >= 1 and forecast_df['month'].max() <= 12, "month should be 1-12"
    
    # Check item_id format (should be customer_facility_product)
    sample_item_id = forecast_df['item_id'].iloc[0]
    parts = sample_item_id.split('_')
    assert len(parts) == 3, f"item_id should have 3 parts separated by underscore, got: {sample_item_id}"
    
    print("✅ prepare_product_forecast_data validation passed")
    print(f"Sample item_id: {sample_item_id}")
    print(f"Sample data:\n{forecast_df.head()}")
    return True

def test_prepare_customer_level_forecast_data():
    """Test the prepare_customer_level_forecast_data function"""
    print("\nTesting prepare_customer_level_forecast_data function...")
    
    # Create sample data
    df = create_sample_data()
    
    # Add temporal features (required by the function)
    df = extract_temporal_features(df)
    
    # Test the function
    forecast_df = prepare_customer_level_forecast_data(df)
    
    # Validate the output
    print(f"Input data shape: {df.shape}")
    print(f"Customer forecast data shape: {forecast_df.shape}")
    print(f"Columns: {list(forecast_df.columns)}")
    
    # Check required columns
    required_columns = [
        'item_id', 'timestamp', 'target_value', 'customer_id', 
        'facility_id', 'metric_type', 'day_of_week', 'month'
    ]
    
    missing_columns = [col for col in required_columns if col not in forecast_df.columns]
    if missing_columns:
        print(f"❌ Missing required columns: {missing_columns}")
        return False
    else:
        print("✅ All required columns present")
    
    # Check metric types
    metric_types = forecast_df['metric_type'].unique()
    expected_metrics = ['TOTAL_UNITS', 'UNIQUE_PRODUCTS', 'TOTAL_VALUE']
    print(f"Metric types found: {metric_types}")
    
    # Check that we have multiple metric types
    assert len(metric_types) >= 2, f"Should have multiple metric types, got: {metric_types}"
    
    # Check item_id format for customer level (should be customer_facility_METRIC)
    sample_item_ids = forecast_df['item_id'].head(3).tolist()
    print(f"Sample item_ids: {sample_item_ids}")
    
    for item_id in sample_item_ids:
        parts = item_id.split('_')
        assert len(parts) >= 3, f"Customer-level item_id should have at least 3 parts, got: {item_id}"
        assert parts[-1] in ['UNITS', 'ITEMS', 'PRODUCTS', 'VALUE'], f"Last part should be metric type, got: {parts[-1]}"
    
    print("✅ prepare_customer_level_forecast_data validation passed")
    print(f"Sample data:\n{forecast_df.head()}")
    return True

def test_data_format_compatibility():
    """Test that the data format is compatible with SageMaker DeepAR requirements"""
    print("\nTesting SageMaker DeepAR format compatibility...")
    
    # Create sample data
    df = create_sample_data()
    df = extract_temporal_features(df)
    
    # Get forecast data
    product_forecast_df = prepare_product_forecast_data(df)
    
    # Test that we can create the basic structure needed for DeepAR
    # Group by item_id to simulate what would be done for DeepAR preparation
    grouped = product_forecast_df.groupby('item_id')
    
    print(f"Number of unique time series: {grouped.ngroups}")
    
    # Check a sample time series
    sample_item = list(grouped.groups.keys())[0]
    sample_series = grouped.get_group(sample_item).sort_values('timestamp')
    
    print(f"Sample time series for {sample_item}:")
    print(f"  - Length: {len(sample_series)}")
    print(f"  - Date range: {sample_series['timestamp'].min()} to {sample_series['timestamp'].max()}")
    print(f"  - Target values range: {sample_series['target_value'].min()} to {sample_series['target_value'].max()}")
    print(f"  - Day of week range: {sample_series['day_of_week'].min()} to {sample_series['day_of_week'].max()}")
    print(f"  - Month range: {sample_series['month'].min()} to {sample_series['month'].max()}")
    
    # Verify we have the components needed for DeepAR JSON format:
    # - start: timestamp of first value ✓
    # - target: array of target values ✓
    # - cat: categorical features (customer_id, facility_id, category) ✓
    # - dynamic_feat: time-dependent features (day_of_week, month) ✓
    
    start_timestamp = sample_series['timestamp'].min().strftime('%Y-%m-%d')
    target_values = sample_series['target_value'].tolist()
    day_of_week_values = sample_series['day_of_week'].tolist()
    month_values = sample_series['month'].tolist()
    
    # Simulate DeepAR format structure
    deepar_sample = {
        "start": start_timestamp,
        "target": target_values,
        "cat": [
            sample_series['customer_id'].iloc[0],
            sample_series['facility_id'].iloc[0], 
            sample_series['category_name'].iloc[0]
        ],
        "dynamic_feat": [
            [d/6 for d in day_of_week_values],  # Normalized day of week
            [(m-1)/11 for m in month_values]    # Normalized month
        ],
        "item_id": sample_item,
        "product_info": {
            "product_id": sample_series['product_id'].iloc[0],
            "product_name": sample_series['product_name'].iloc[0],
            "category_name": sample_series['category_name'].iloc[0],
            "customer_id": sample_series['customer_id'].iloc[0],
            "facility_id": sample_series['facility_id'].iloc[0]
        }
    }
    
    print(f"✅ Successfully created DeepAR-compatible structure")
    print(f"Sample DeepAR format (first 5 target values): {deepar_sample['target'][:5]}")
    print(f"Dynamic features shape: {len(deepar_sample['dynamic_feat'])} x {len(deepar_sample['dynamic_feat'][0])}")
    
    return True

def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing Forecast Data Preparation Functions")
    print("=" * 60)
    
    try:
        # Test product-level forecast data preparation
        success1 = test_prepare_product_forecast_data()
        
        # Test customer-level forecast data preparation  
        success2 = test_prepare_customer_level_forecast_data()
        
        # Test SageMaker DeepAR format compatibility
        success3 = test_data_format_compatibility()
        
        if success1 and success2 and success3:
            print("\n" + "=" * 60)
            print("✅ ALL TESTS PASSED - Functions are ready for SageMaker DeepAR")
            print("=" * 60)
            return True
        else:
            print("\n" + "=" * 60)
            print("❌ SOME TESTS FAILED")
            print("=" * 60)
            return False
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)