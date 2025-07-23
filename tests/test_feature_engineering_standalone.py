#!/usr/bin/env python3
"""
Standalone Unit Tests for Enhanced Feature Engineering Functions

This test suite validates the feature engineering logic without AWS dependencies.
Tests are designed to match the notebook's expected outputs and behavior.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, date
import sys

# Standalone implementations of the functions for testing
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

def calculate_product_demand_patterns(df):
    """Calculate product-specific demand patterns for individual products"""
    # Group by customer, facility, product, and date to get daily quantities
    if 'OrderUnits' in df.columns:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date'])['OrderUnits'].sum().reset_index(name='Quantity')
    else:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information back
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
    
    # Calculate product-specific features
    product_groups = product_daily.groupby(['CustomerID', 'FacilityID', 'ProductID'])
    
    product_features = []
    for (customer_id, facility_id, product_id), group in product_groups:
        # Sort by date
        group_sorted = group.sort_values('Date')
        
        # Calculate basic statistics
        total_orders = len(group_sorted)
        avg_quantity = group_sorted['Quantity'].mean()
        std_quantity = group_sorted['Quantity'].std()
        max_quantity = group_sorted['Quantity'].max()
        min_quantity = group_sorted['Quantity'].min()
        median_quantity = group_sorted['Quantity'].median()
        
        # Calculate order frequency (days between orders)
        if total_orders > 1:
            date_range = (pd.to_datetime(group_sorted['Date'].max()) - pd.to_datetime(group_sorted['Date'].min())).days
            avg_days_between_orders = date_range / (total_orders - 1) if total_orders > 1 else np.nan
        else:
            avg_days_between_orders = np.nan
        
        # Calculate coefficient of variation (volatility measure)
        cv = std_quantity / avg_quantity if avg_quantity > 0 else 0
        
        # Calculate trend (simple linear trend over time)
        if total_orders > 2:
            dates_numeric = pd.to_datetime(group_sorted['Date']).astype(int) / 10**9  # Convert to seconds
            trend_slope = np.polyfit(dates_numeric, group_sorted['Quantity'], 1)[0]
        else:
            trend_slope = 0
        
        # Get product info with fallback names
        product_name = ''
        if 'ProductDescription' in group_sorted.columns:
            product_name = group_sorted['ProductDescription'].iloc[0]
        elif 'ProductName' in group_sorted.columns:
            product_name = group_sorted['ProductName'].iloc[0]
        
        category_name = ''
        if 'ProductCategory' in group_sorted.columns:
            category_name = group_sorted['ProductCategory'].iloc[0]
        elif 'CategoryName' in group_sorted.columns:
            category_name = group_sorted['CategoryName'].iloc[0]
        
        vendor_name = ''
        if 'VendorName' in group_sorted.columns:
            vendor_name = group_sorted['VendorName'].iloc[0]
        
        # Get first and last order dates
        first_order_date = group_sorted['Date'].min()
        last_order_date = group_sorted['Date'].max()
        
        product_features.append({
            'CustomerID': customer_id,
            'FacilityID': facility_id,
            'ProductID': product_id,
            'ProductName': product_name,
            'CategoryName': category_name,
            'VendorName': vendor_name,
            'TotalOrders': total_orders,
            'AvgQuantity': avg_quantity,
            'StdQuantity': std_quantity if not pd.isna(std_quantity) else 0,
            'MaxQuantity': max_quantity,
            'MinQuantity': min_quantity,
            'MedianQuantity': median_quantity,
            'CoefficientOfVariation': cv,
            'TrendSlope': trend_slope,
            'AvgDaysBetweenOrders': avg_days_between_orders,
            'FirstOrderDate': first_order_date,
            'LastOrderDate': last_order_date
        })
    
    return pd.DataFrame(product_features)

def prepare_product_forecast_data(df):
    """Prepare data for product-level forecasting in SageMaker DeepAR format"""
    # Group by customer, facility, product, and date to get daily quantities
    if 'OrderUnits' in df.columns:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date'])['OrderUnits'].sum().reset_index(name='Quantity')
    else:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information
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
    
    # Add temporal features required for SageMaker DeepAR
    forecast_df['day_of_week'] = forecast_df['timestamp'].dt.dayofweek
    forecast_df['month'] = forecast_df['timestamp'].dt.month
    
    # Sort by item_id and timestamp for proper time series format
    forecast_df = forecast_df.sort_values(['item_id', 'timestamp']).reset_index(drop=True)
    
    return forecast_df

def create_product_lookup_table(df):
    """Create a lookup table for product information matching notebook schema"""
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
    customer_product_lookup = customer_product_lookup[[
        'ProductID', 'ProductName', 'CategoryName', 'vendorName', 
        'CustomerID', 'FacilityID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate'
    ]]
    
    return product_lookup, customer_product_lookup

class TestFeatureEngineering(unittest.TestCase):
    """Test cases for feature engineering functions"""
    
    def setUp(self):
        """Set up test data that matches notebook format"""
        # Create sample data matching the notebook's CSV structure
        self.sample_data = pd.DataFrame({
            'CustomerID': [1045, 1045, 1045, 1045, 1045, 1046, 1046],
            'FacilityID': [6420, 6417, 6417, 6359, 4745, 6420, 6417],
            'OrderID': [9149870, 9148894, 9635115, 9626004, 9854860, 9149871, 9148895],
            'ProductID': [288563, 288563, 288563, 288563, 288563, 288564, 288564],
            'ProductName': ['Cereal Toasty Os (Cheerios)', 'Cereal Toasty Os (Cheerios)', 
                          'Cereal Toasty Os (Cheerios)', 'Cereal Toasty Os (Cheerios)',
                          'Cereal Toasty Os (Cheerios)', 'Milk Whole', 'Milk Whole'],
            'CategoryName': ['Cereals', 'Cereals', 'Cereals', 'Cereals', 'Cereals', 'Dairy', 'Dairy'],
            'VendorName': ['US FoodsBuffalo (HPSI)', 'US FoodsBuffalo (HPSI)', 'US FoodsBuffalo (HPSI)',
                          'US FoodsBuffalo (HPSI)', 'US FoodsBuffalo (HPSI)', 'Dairy Co', 'Dairy Co'],
            'CreateDate': ['07/08/2024', '07/08/2024', '10/21/2024', '10/15/2024', '12/04/2024', '07/09/2024', '07/10/2024'],
            'OrderUnits': [1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 3.0],
            'Price': [23.17, 23.17, 23.17, 23.17, 23.17, 4.50, 4.50]
        })
        
        # Convert dates to datetime
        self.sample_data['CreateDate'] = pd.to_datetime(self.sample_data['CreateDate'])
        
        # Expected temporal features for validation (based on notebook logic)
        self.expected_temporal_features = {
            'OrderYear': [2024, 2024, 2024, 2024, 2024, 2024, 2024],
            'OrderMonth': [7, 7, 10, 10, 12, 7, 7],
            'OrderDay': [8, 8, 21, 15, 4, 9, 10],
            'OrderDayOfWeek': [0, 0, 0, 1, 2, 1, 2],  # Monday=0
            'IsWeekend': [0, 0, 0, 0, 0, 0, 0]
        }
    
    def test_temporal_feature_extraction(self):
        """Test temporal feature extraction matches notebook implementation"""
        print("\n=== Testing Temporal Feature Extraction ===")
        
        # Apply temporal feature extraction
        result_df = extract_temporal_features(self.sample_data.copy())
        
        # Test basic date components
        for feature, expected_values in self.expected_temporal_features.items():
            with self.subTest(feature=feature):
                actual_values = result_df[feature].tolist()
                self.assertEqual(actual_values, expected_values, 
                               f"Feature {feature} doesn't match expected values")
                print(f"✓ {feature}: {actual_values}")
        
        # Test cyclical encoding (sin/cos values should be between -1 and 1)
        cyclical_features = ['DayOfWeek_sin', 'DayOfWeek_cos', 'MonthOfYear_sin', 
                           'MonthOfYear_cos', 'DayOfMonth_sin', 'DayOfMonth_cos']
        
        for feature in cyclical_features:
            with self.subTest(feature=feature):
                values = result_df[feature]
                self.assertTrue(all(values >= -1.0), f"{feature} has values < -1")
                self.assertTrue(all(values <= 1.0), f"{feature} has values > 1")
                print(f"✓ {feature}: range [{values.min():.3f}, {values.max():.3f}]")
        
        # Test specific cyclical encoding values for Monday (day 0)
        monday_rows = result_df[result_df['OrderDayOfWeek'] == 0]
        expected_sin = np.sin(0 * (2 * np.pi / 7))  # Should be 0
        expected_cos = np.cos(0 * (2 * np.pi / 7))  # Should be 1
        
        self.assertAlmostEqual(monday_rows['DayOfWeek_sin'].iloc[0], expected_sin, places=5)
        self.assertAlmostEqual(monday_rows['DayOfWeek_cos'].iloc[0], expected_cos, places=5)
        print(f"✓ Monday cyclical encoding: sin={expected_sin:.3f}, cos={expected_cos:.3f}")
        
        # Test quarter calculation
        expected_quarters = [3, 3, 4, 4, 4, 3, 3]  # July=Q3, October=Q4, December=Q4
        actual_quarters = result_df['OrderQuarter'].tolist()
        self.assertEqual(actual_quarters, expected_quarters)
        print(f"✓ Quarters: {actual_quarters}")
        
        print("✓ All temporal feature extraction tests passed!")
    
    def test_dynamic_holiday_detection(self):
        """Test dynamic holiday detection for multiple years"""
        print("\n=== Testing Dynamic Holiday Detection ===")
        
        # Test holiday detection for 2024
        holidays_2024 = get_us_holidays(2024)
        
        # Test fixed holidays
        expected_fixed_holidays = {
            '2024-01-01': "New Year's Day",
            '2024-06-19': "Juneteenth",
            '2024-07-04': "Independence Day",
            '2024-11-11': "Veterans Day",
            '2024-12-25': "Christmas Day"
        }
        
        for date_str, holiday_name in expected_fixed_holidays.items():
            with self.subTest(holiday=holiday_name):
                self.assertIn(date_str, holidays_2024)
                self.assertEqual(holidays_2024[date_str], holiday_name)
                print(f"✓ {date_str}: {holiday_name}")
        
        # Test variable holidays for 2024 (verify they fall on correct days)
        # Martin Luther King Jr. Day - 3rd Monday in January 2024
        mlk_date = None
        for date_str, name in holidays_2024.items():
            if name == "Martin Luther King Jr. Day":
                mlk_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                break
        
        self.assertIsNotNone(mlk_date, "MLK Day not found")
        self.assertEqual(mlk_date.weekday(), 0, "MLK Day should be on Monday")  # Monday = 0
        self.assertEqual(mlk_date.month, 1, "MLK Day should be in January")
        print(f"✓ MLK Day 2024: {mlk_date} (Monday)")
        
        # Test different year (2025) to ensure dynamic calculation
        holidays_2025 = get_us_holidays(2025)
        self.assertIn('2025-01-01', holidays_2025)
        self.assertIn('2025-07-04', holidays_2025)
        
        # Verify 2024 and 2025 have different variable holiday dates
        mlk_2025 = None
        for date_str, name in holidays_2025.items():
            if name == "Martin Luther King Jr. Day":
                mlk_2025 = datetime.strptime(date_str, '%Y-%m-%d').date()
                break
        
        self.assertNotEqual(mlk_date, mlk_2025, "MLK Day should be different between years")
        print(f"✓ MLK Day 2025: {mlk_2025} (different from 2024)")
        
        print("✓ All holiday detection tests passed!")
    
    def test_product_demand_patterns(self):
        """Test product demand pattern calculations"""
        print("\n=== Testing Product Demand Pattern Calculations ===")
        
        # Apply temporal features first (needed for Date column)
        df_with_features = extract_temporal_features(self.sample_data.copy())
        
        # Calculate product demand patterns
        product_patterns = calculate_product_demand_patterns(df_with_features)
        
        # Test basic structure
        expected_columns = [
            'CustomerID', 'FacilityID', 'ProductID', 'ProductName', 'CategoryName', 
            'VendorName', 'TotalOrders', 'AvgQuantity', 'StdQuantity', 'MaxQuantity',
            'MinQuantity', 'MedianQuantity', 'CoefficientOfVariation', 'TrendSlope',
            'AvgDaysBetweenOrders', 'FirstOrderDate', 'LastOrderDate'
        ]
        
        for col in expected_columns:
            with self.subTest(column=col):
                self.assertIn(col, product_patterns.columns, f"Missing column: {col}")
        
        print(f"✓ Product patterns shape: {product_patterns.shape}")
        print(f"✓ All expected columns present: {len(expected_columns)}")
        
        # Test specific calculations for Product 288563 (Cheerios)
        cheerios_pattern = product_patterns[
            (product_patterns['ProductID'] == 288563) & 
            (product_patterns['CustomerID'] == 1045)
        ]
        
        self.assertFalse(cheerios_pattern.empty, "Cheerios pattern not found")
        
        # Should have multiple facilities for this product
        cheerios_facilities = cheerios_pattern['FacilityID'].unique()
        self.assertGreater(len(cheerios_facilities), 1, "Should have multiple facilities")
        print(f"✓ Cheerios found in {len(cheerios_facilities)} facilities")
        
        # Test calculations for one facility
        facility_pattern = cheerios_pattern.iloc[0]
        
        # Basic validations
        self.assertGreater(facility_pattern['TotalOrders'], 0)
        self.assertGreater(facility_pattern['AvgQuantity'], 0)
        self.assertGreaterEqual(facility_pattern['StdQuantity'], 0)
        self.assertEqual(facility_pattern['ProductName'], 'Cereal Toasty Os (Cheerios)')
        self.assertEqual(facility_pattern['CategoryName'], 'Cereals')
        
        print(f"✓ Total orders: {facility_pattern['TotalOrders']}")
        print(f"✓ Avg quantity: {facility_pattern['AvgQuantity']:.2f}")
        print(f"✓ Product name: {facility_pattern['ProductName']}")
        
        print("✓ All product demand pattern tests passed!")
    
    def test_product_forecast_data_preparation(self):
        """Test product-level forecast data preparation for SageMaker"""
        print("\n=== Testing Product Forecast Data Preparation ===")
        
        # Apply temporal features first
        df_with_features = extract_temporal_features(self.sample_data.copy())
        
        # Prepare forecast data
        forecast_df = prepare_product_forecast_data(df_with_features)
        
        # Test structure
        expected_columns = [
            'item_id', 'timestamp', 'target_value', 'customer_id', 'facility_id',
            'product_id', 'product_name', 'category_name', 'vendor_name',
            'day_of_week', 'month'
        ]
        
        for col in expected_columns:
            with self.subTest(column=col):
                self.assertIn(col, forecast_df.columns, f"Missing column: {col}")
        
        print(f"✓ Forecast data shape: {forecast_df.shape}")
        print(f"✓ All expected columns present: {len(expected_columns)}")
        
        # Test item_id format (should be customer_facility_product)
        sample_item_id = forecast_df['item_id'].iloc[0]
        parts = sample_item_id.split('_')
        self.assertEqual(len(parts), 3, f"item_id should have 3 parts: {sample_item_id}")
        
        # Verify item_id components match the row data
        row = forecast_df.iloc[0]
        expected_item_id = f"{row['customer_id']}_{row['facility_id']}_{row['product_id']}"
        self.assertEqual(row['item_id'], expected_item_id)
        print(f"✓ Item ID format: {sample_item_id}")
        
        # Test timestamp format
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(forecast_df['timestamp']))
        print(f"✓ Timestamp format: {forecast_df['timestamp'].iloc[0]}")
        
        # Test target_value (should be positive)
        self.assertTrue(all(forecast_df['target_value'] > 0))
        print(f"✓ Target values range: [{forecast_df['target_value'].min()}, {forecast_df['target_value'].max()}]")
        
        print("✓ All product forecast data preparation tests passed!")
    
    def test_product_lookup_table_creation(self):
        """Test product lookup table creation matching notebook schema"""
        print("\n=== Testing Product Lookup Table Creation ===")
        
        # Apply temporal features first
        df_with_features = extract_temporal_features(self.sample_data.copy())
        
        # Create lookup tables
        product_lookup, customer_product_lookup = create_product_lookup_table(df_with_features)
        
        # Test product lookup structure
        expected_product_columns = ['ProductID', 'ProductName', 'CategoryName', 'vendorName']
        
        for col in expected_product_columns:
            with self.subTest(column=col):
                self.assertIn(col, product_lookup.columns, f"Missing product lookup column: {col}")
        
        print(f"✓ Product lookup shape: {product_lookup.shape}")
        print(f"✓ Product lookup columns: {list(product_lookup.columns)}")
        
        # Test customer-product lookup structure (notebook schema)
        expected_customer_product_columns = [
            'ProductID', 'ProductName', 'CategoryName', 'vendorName',
            'CustomerID', 'FacilityID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate'
        ]
        
        for col in expected_customer_product_columns:
            with self.subTest(column=col):
                self.assertIn(col, customer_product_lookup.columns, 
                            f"Missing customer-product lookup column: {col}")
        
        print(f"✓ Customer-product lookup shape: {customer_product_lookup.shape}")
        
        # Test data integrity
        # Product lookup should have unique products
        self.assertEqual(len(product_lookup), product_lookup['ProductID'].nunique())
        print(f"✓ Product lookup has {len(product_lookup)} unique products")
        
        # Test specific data values
        cheerios_product = product_lookup[product_lookup['ProductID'] == 288563]
        self.assertFalse(cheerios_product.empty, "Cheerios product not found in lookup")
        
        cheerios_row = cheerios_product.iloc[0]
        self.assertEqual(cheerios_row['ProductName'], 'Cereal Toasty Os (Cheerios)')
        self.assertEqual(cheerios_row['CategoryName'], 'Cereals')
        self.assertEqual(cheerios_row['vendorName'], 'US FoodsBuffalo (HPSI)')
        print(f"✓ Cheerios lookup: {cheerios_row['ProductName']} - {cheerios_row['CategoryName']}")
        
        print("✓ All product lookup table creation tests passed!")

def run_feature_engineering_tests():
    """Run all feature engineering unit tests"""
    print("=" * 60)
    print("FEATURE ENGINEERING UNIT TESTS")
    print("=" * 60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFeatureEngineering)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall result: {'PASS' if success else 'FAIL'}")
    
    return success

if __name__ == '__main__':
    success = run_feature_engineering_tests()
    sys.exit(0 if success else 1)