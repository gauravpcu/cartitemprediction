#!/usr/bin/env python3
"""
Unit tests for Enhanced Feature Engineering Lambda Function

This test suite validates that the Lambda function implementations match
the notebook's feature engineering logic and produce consistent results.

Test Coverage:
- Temporal feature extraction with cyclical encoding
- Dynamic holiday detection for multiple years
- Product demand pattern calculations
- Lookup table generation
- Forecast data preparation
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, date
import sys
import os
import tempfile
import json

# Add the function directory to the path
sys.path.append('functions/enhanced_feature_engineering')
from app import (
    extract_temporal_features,
    get_us_holidays,
    calculate_product_demand_patterns,
    prepare_product_forecast_data,
    prepare_customer_level_forecast_data,
    create_product_lookup_table
)

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
        
        # Test that Date column is created
        self.assertIn('Date', result_df.columns)
        self.assertTrue(all(result_df['Date'].str.match(r'\d{4}-\d{2}-\d{2}')))
        print(f"✓ Date format: {result_df['Date'].iloc[0]}")
        
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
        
        # Test Thanksgiving - 4th Thursday in November 2024
        thanksgiving_date = None
        for date_str, name in holidays_2024.items():
            if name == "Thanksgiving Day":
                thanksgiving_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                break
        
        self.assertIsNotNone(thanksgiving_date, "Thanksgiving not found")
        self.assertEqual(thanksgiving_date.weekday(), 3, "Thanksgiving should be on Thursday")  # Thursday = 3
        self.assertEqual(thanksgiving_date.month, 11, "Thanksgiving should be in November")
        print(f"✓ Thanksgiving 2024: {thanksgiving_date} (Thursday)")
        
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
        
        # Test holiday detection in sample data
        result_df = extract_temporal_features(self.sample_data.copy())
        
        # Check if any of our sample dates are holidays
        holiday_flags = result_df['IsHoliday'].tolist()
        holiday_names = result_df['HolidayName'].tolist()
        
        print(f"✓ Holiday flags in sample data: {holiday_flags}")
        print(f"✓ Holiday names in sample data: {holiday_names}")
        
        # July 4th, 2024 should be a holiday if it's in our data
        july_4_rows = result_df[result_df['Date'] == '2024-07-04']
        if not july_4_rows.empty:
            self.assertEqual(july_4_rows['IsHoliday'].iloc[0], 1)
            self.assertEqual(july_4_rows['HolidayName'].iloc[0], "Independence Day")
            print("✓ July 4th correctly identified as Independence Day")
        
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
        print(f"✓ Std quantity: {facility_pattern['StdQuantity']:.2f}")
        print(f"✓ Product name: {facility_pattern['ProductName']}")
        
        # Test date fields
        self.assertIsInstance(facility_pattern['FirstOrderDate'], str)
        self.assertIsInstance(facility_pattern['LastOrderDate'], str)
        
        # First order should be before or equal to last order
        first_date = pd.to_datetime(facility_pattern['FirstOrderDate'])
        last_date = pd.to_datetime(facility_pattern['LastOrderDate'])
        self.assertLessEqual(first_date, last_date)
        
        print(f"✓ Date range: {facility_pattern['FirstOrderDate']} to {facility_pattern['LastOrderDate']}")
        
        # Test coefficient of variation calculation
        if facility_pattern['AvgQuantity'] > 0:
            expected_cv = facility_pattern['StdQuantity'] / facility_pattern['AvgQuantity']
            self.assertAlmostEqual(facility_pattern['CoefficientOfVariation'], expected_cv, places=5)
            print(f"✓ Coefficient of variation: {facility_pattern['CoefficientOfVariation']:.3f}")
        
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
        
        # Test temporal features for SageMaker
        self.assertTrue(all(forecast_df['day_of_week'].between(0, 6)))
        self.assertTrue(all(forecast_df['month'].between(1, 12)))
        print(f"✓ Day of week range: [{forecast_df['day_of_week'].min()}, {forecast_df['day_of_week'].max()}]")
        print(f"✓ Month range: [{forecast_df['month'].min()}, {forecast_df['month'].max()}]")
        
        # Test sorting (should be sorted by item_id and timestamp)
        is_sorted = forecast_df.equals(forecast_df.sort_values(['item_id', 'timestamp']))
        self.assertTrue(is_sorted, "Forecast data should be sorted by item_id and timestamp")
        print("✓ Data is properly sorted")
        
        print("✓ All product forecast data preparation tests passed!")
    
    def test_customer_level_forecast_data_preparation(self):
        """Test customer-level forecast data preparation"""
        print("\n=== Testing Customer-Level Forecast Data Preparation ===")
        
        # Apply temporal features first
        df_with_features = extract_temporal_features(self.sample_data.copy())
        
        # Prepare customer-level forecast data
        customer_forecast_df = prepare_customer_level_forecast_data(df_with_features)
        
        # Test structure
        expected_columns = [
            'item_id', 'timestamp', 'target_value', 'customer_id', 'facility_id',
            'metric_type', 'day_of_week', 'month'
        ]
        
        for col in expected_columns:
            with self.subTest(column=col):
                self.assertIn(col, customer_forecast_df.columns, f"Missing column: {col}")
        
        print(f"✓ Customer forecast data shape: {customer_forecast_df.shape}")
        
        # Test metric types
        metric_types = customer_forecast_df['metric_type'].unique()
        expected_metrics = ['TOTAL_UNITS', 'UNIQUE_PRODUCTS', 'TOTAL_VALUE']
        
        for metric in expected_metrics:
            with self.subTest(metric=metric):
                self.assertIn(metric, metric_types, f"Missing metric type: {metric}")
        
        print(f"✓ Metric types: {list(metric_types)}")
        
        # Test item_id format for customer-level data
        sample_item_id = customer_forecast_df['item_id'].iloc[0]
        parts = sample_item_id.split('_')
        self.assertGreaterEqual(len(parts), 4, f"Customer item_id should have at least 4 parts: {sample_item_id}")
        
        # Should end with metric type
        metric_part = '_'.join(parts[2:])  # Everything after customer_facility
        self.assertIn(metric_part, expected_metrics)
        print(f"✓ Customer item ID format: {sample_item_id}")
        
        # Test that we have data for each customer-facility combination
        customer_facility_combos = df_with_features[['CustomerID', 'FacilityID']].drop_duplicates()
        expected_records = len(customer_facility_combos) * len(expected_metrics)
        
        # Should have records for each date as well, so actual count will be higher
        unique_item_ids = customer_forecast_df['item_id'].nunique()
        self.assertGreaterEqual(unique_item_ids, expected_records)
        print(f"✓ Unique item IDs: {unique_item_ids} (expected at least {expected_records})")
        
        print("✓ All customer-level forecast data preparation tests passed!")
    
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
        print(f"✓ Customer-product lookup columns: {list(customer_product_lookup.columns)}")
        
        # Test data integrity
        # Product lookup should have unique products
        self.assertEqual(len(product_lookup), product_lookup['ProductID'].nunique())
        print(f"✓ Product lookup has {len(product_lookup)} unique products")
        
        # Customer-product lookup should have unique combinations
        combo_cols = ['CustomerID', 'FacilityID', 'ProductID']
        unique_combos = customer_product_lookup[combo_cols].drop_duplicates()
        self.assertEqual(len(customer_product_lookup), len(unique_combos))
        print(f"✓ Customer-product lookup has {len(customer_product_lookup)} unique combinations")
        
        # Test specific data values
        cheerios_product = product_lookup[product_lookup['ProductID'] == 288563]
        self.assertFalse(cheerios_product.empty, "Cheerios product not found in lookup")
        
        cheerios_row = cheerios_product.iloc[0]
        self.assertEqual(cheerios_row['ProductName'], 'Cereal Toasty Os (Cheerios)')
        self.assertEqual(cheerios_row['CategoryName'], 'Cereals')
        self.assertEqual(cheerios_row['vendorName'], 'US FoodsBuffalo (HPSI)')
        print(f"✓ Cheerios lookup: {cheerios_row['ProductName']} - {cheerios_row['CategoryName']}")
        
        # Test customer-product relationship data
        cheerios_relationships = customer_product_lookup[customer_product_lookup['ProductID'] == 288563]
        self.assertFalse(cheerios_relationships.empty, "Cheerios relationships not found")
        
        # Should have multiple customer-facility combinations for Cheerios
        cheerios_combos = cheerios_relationships[['CustomerID', 'FacilityID']].drop_duplicates()
        self.assertGreater(len(cheerios_combos), 1, "Should have multiple customer-facility combinations")
        print(f"✓ Cheerios found in {len(cheerios_combos)} customer-facility combinations")
        
        # Test order count calculations
        sample_relationship = cheerios_relationships.iloc[0]
        self.assertGreater(sample_relationship['OrderCount'], 0)
        print(f"✓ Sample order count: {sample_relationship['OrderCount']}")
        
        # Test date fields are properly formatted
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(
            pd.to_datetime(customer_product_lookup['FirstOrderDate'])))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(
            pd.to_datetime(customer_product_lookup['LastOrderDate'])))
        print("✓ Date fields are properly formatted")
        
        print("✓ All product lookup table creation tests passed!")
    
    def test_notebook_consistency(self):
        """Test that outputs match expected notebook format and structure"""
        print("\n=== Testing Notebook Consistency ===")
        
        # Process the full pipeline
        df_with_features = extract_temporal_features(self.sample_data.copy())
        product_patterns = calculate_product_demand_patterns(df_with_features)
        product_forecast = prepare_product_forecast_data(df_with_features)
        customer_forecast = prepare_customer_level_forecast_data(df_with_features)
        product_lookup, customer_product_lookup = create_product_lookup_table(df_with_features)
        
        # Test that all outputs are DataFrames
        outputs = {
            'df_with_features': df_with_features,
            'product_patterns': product_patterns,
            'product_forecast': product_forecast,
            'customer_forecast': customer_forecast,
            'product_lookup': product_lookup,
            'customer_product_lookup': customer_product_lookup
        }
        
        for name, output in outputs.items():
            with self.subTest(output=name):
                self.assertIsInstance(output, pd.DataFrame, f"{name} should be a DataFrame")
                self.assertGreater(len(output), 0, f"{name} should not be empty")
        
        print("✓ All outputs are non-empty DataFrames")
        
        # Test that temporal features match expected mathematical relationships
        # For cyclical encoding: sin^2 + cos^2 should equal 1
        for prefix in ['DayOfWeek', 'MonthOfYear', 'DayOfMonth']:
            sin_col = f'{prefix}_sin'
            cos_col = f'{prefix}_cos'
            
            if sin_col in df_with_features.columns and cos_col in df_with_features.columns:
                sin_squared = df_with_features[sin_col] ** 2
                cos_squared = df_with_features[cos_col] ** 2
                sum_squares = sin_squared + cos_squared
                
                # Should be approximately 1 (within floating point precision)
                self.assertTrue(all(abs(sum_squares - 1.0) < 1e-10), 
                              f"sin^2 + cos^2 should equal 1 for {prefix}")
                print(f"✓ {prefix} cyclical encoding: sin^2 + cos^2 = 1")
        
        # Test data type consistency
        # Numeric columns should be numeric
        numeric_columns = ['OrderYear', 'OrderMonth', 'OrderDay', 'OrderDayOfWeek', 
                          'IsWeekend', 'IsHoliday', 'OrderQuarter']
        
        for col in numeric_columns:
            if col in df_with_features.columns:
                self.assertTrue(pd.api.types.is_numeric_dtype(df_with_features[col]), 
                              f"{col} should be numeric")
        
        print("✓ All numeric columns have correct data types")
        
        # Test that forecast data has proper time series structure
        # Each item_id should have chronologically ordered timestamps
        for item_id in product_forecast['item_id'].unique()[:3]:  # Test first 3 items
            item_data = product_forecast[product_forecast['item_id'] == item_id]
            timestamps = item_data['timestamp'].tolist()
            sorted_timestamps = sorted(timestamps)
            self.assertEqual(timestamps, sorted_timestamps, 
                           f"Timestamps not sorted for item {item_id}")
        
        print("✓ Forecast data has proper time series structure")
        
        print("✓ All notebook consistency tests passed!")

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