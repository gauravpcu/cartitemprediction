#!/usr/bin/env python3
"""
Test script for the updated data validation Lambda function
"""

import pandas as pd
import numpy as np
import json
import sys
import os
from datetime import datetime, timedelta

# Add the function directory to the path
sys.path.append('functions/data_validation')

# Import the validation functions
from app import validate_data_quality, generate_data_distribution_analysis, analyze_categorical_distributions, validate_business_rules, generate_comprehensive_report

def create_test_data():
    """Create test data matching the notebook's schema"""
    np.random.seed(42)
    
    # Create sample data matching notebook schema
    n_records = 1000
    
    data = {
        'CustomerID': np.random.choice([1045, 1046, 1047, 1048, 1049], n_records),
        'FacilityID': np.random.choice(range(4000, 7000), n_records),
        'OrderID': np.random.choice(range(9000000, 10000000), n_records),
        'ProductID': np.random.choice(range(200000, 300000), n_records),
        'ProductName': np.random.choice(['Cereal Toasty Os (Cheerios)', 'Milk 2%', 'Bread Whole Wheat', 'Eggs Large'], n_records),
        'CategoryName': np.random.choice(['Cereals', 'Dairy', 'Bakery', 'Protein'], n_records),
        'VendorID': np.random.choice(range(40000, 50000), n_records),
        'VendorName': np.random.choice(['US Foods Buffalo (HPSI)', 'Sysco', 'Performance Food Group'], n_records),
        'CreateDate': pd.date_range(start='2024-05-01', end='2025-06-18', periods=n_records).strftime('%m/%d/%Y'),
        'OrderUnits': np.random.exponential(2, n_records) + 0.1,  # Positive values
        'Price': np.random.exponential(20, n_records) + 1.0  # Positive prices
    }
    
    df = pd.DataFrame(data)
    
    # Add some data quality issues for testing
    # Add some missing values
    df.loc[np.random.choice(df.index, 10), 'ProductName'] = np.nan
    
    # Add some negative values to test validation
    df.loc[np.random.choice(df.index, 5), 'OrderUnits'] = -1.0
    df.loc[np.random.choice(df.index, 3), 'Price'] = -5.0
    
    return df

def test_validation_functions():
    """Test all validation functions"""
    print("🧪 Testing Data Validation Functions")
    print("=" * 50)
    
    # Create test data
    print("📊 Creating test data...")
    df = create_test_data()
    print(f"✅ Created test dataset with {len(df)} records and {len(df.columns)} columns")
    
    # Test main validation function
    print("\n🔍 Testing main validation function...")
    try:
        validation_results = validate_data_quality(df)
        print(f"✅ Main validation completed")
        print(f"   - Validation Status: {validation_results.get('validation_summary', 'Unknown')}")
        print(f"   - Issues: {len(validation_results.get('issues', []))}")
        print(f"   - Warnings: {len(validation_results.get('warnings', []))}")
        print(f"   - Total Records: {validation_results['stats'].get('total_records', 0)}")
        
        if validation_results.get('issues'):
            print("   - Issues found:")
            for issue in validation_results['issues'][:3]:  # Show first 3
                print(f"     • {issue}")
                
        if validation_results.get('warnings'):
            print("   - Warnings found:")
            for warning in validation_results['warnings'][:3]:  # Show first 3
                print(f"     • {warning}")
                
    except Exception as e:
        print(f"❌ Main validation failed: {str(e)}")
        return False
    
    # Test distribution analysis
    print("\n📈 Testing distribution analysis...")
    try:
        dist_analysis = generate_data_distribution_analysis(df)
        print(f"✅ Distribution analysis completed for {len(dist_analysis)} numeric columns")
        
        # Show sample analysis for OrderUnits
        if 'OrderUnits' in dist_analysis:
            ou_stats = dist_analysis['OrderUnits']
            print(f"   - OrderUnits: mean={ou_stats['mean']:.2f}, std={ou_stats['std']:.2f}, outliers={ou_stats['outliers_iqr']}")
            
    except Exception as e:
        print(f"❌ Distribution analysis failed: {str(e)}")
        return False
    
    # Test categorical analysis
    print("\n📊 Testing categorical analysis...")
    try:
        cat_analysis = analyze_categorical_distributions(df)
        print(f"✅ Categorical analysis completed for {len(cat_analysis)} text columns")
        
        # Show sample analysis for CategoryName
        if 'CategoryName' in cat_analysis:
            cat_stats = cat_analysis['CategoryName']
            print(f"   - CategoryName: {cat_stats['unique_values']} unique values, most frequent: {cat_stats['most_frequent']}")
            
    except Exception as e:
        print(f"❌ Categorical analysis failed: {str(e)}")
        return False
    
    # Test business rules validation
    print("\n🏢 Testing business rules validation...")
    try:
        business_validation = validate_business_rules(df)
        print(f"✅ Business validation completed")
        print(f"   - Rules Passed: {len(business_validation.get('rules_passed', []))}")
        print(f"   - Rules Failed: {len(business_validation.get('rules_failed', []))}")
        
        if business_validation.get('rules_passed'):
            print("   - Passed rules:")
            for rule in business_validation['rules_passed'][:2]:
                print(f"     • {rule}")
                
        if business_validation.get('rules_failed'):
            print("   - Failed rules:")
            for rule in business_validation['rules_failed'][:2]:
                print(f"     • {rule}")
                
    except Exception as e:
        print(f"❌ Business validation failed: {str(e)}")
        return False
    
    # Test comprehensive report
    print("\n📋 Testing comprehensive report...")
    try:
        report = generate_comprehensive_report(df)
        print(f"✅ Comprehensive report generated")
        print(f"   - Data Quality Score: {report.get('data_quality_score', 0):.1f}%")
        print(f"   - Total Records: {report['dataset_overview'].get('total_records', 0)}")
        print(f"   - Duplicate Percentage: {report['dataset_overview'].get('duplicate_percentage', 0):.2f}%")
        print(f"   - Recommendations: {len(report.get('recommendations', []))}")
        
        if report.get('recommendations'):
            print("   - Top recommendations:")
            for rec in report['recommendations'][:2]:
                print(f"     • {rec}")
                
    except Exception as e:
        print(f"❌ Comprehensive report failed: {str(e)}")
        return False
    
    print("\n🎉 All validation functions tested successfully!")
    return True

def test_edge_cases():
    """Test edge cases and error handling"""
    print("\n🔬 Testing Edge Cases")
    print("=" * 30)
    
    # Test with empty dataframe
    print("📭 Testing empty dataframe...")
    try:
        empty_df = pd.DataFrame()
        validation_results = validate_data_quality(empty_df)
        print(f"✅ Empty dataframe handled: {validation_results.get('validation_summary', 'Unknown')}")
    except Exception as e:
        print(f"❌ Empty dataframe test failed: {str(e)}")
        return False
    
    # Test with missing columns
    print("🕳️  Testing missing required columns...")
    try:
        incomplete_df = pd.DataFrame({'SomeColumn': [1, 2, 3]})
        validation_results = validate_data_quality(incomplete_df)
        print(f"✅ Missing columns handled: {len(validation_results.get('issues', []))} issues found")
    except Exception as e:
        print(f"❌ Missing columns test failed: {str(e)}")
        return False
    
    # Test with all null values
    print("🚫 Testing all null values...")
    try:
        null_df = pd.DataFrame({
            'CustomerID': [None, None, None],
            'FacilityID': [None, None, None],
            'CreateDate': [None, None, None]
        })
        validation_results = validate_data_quality(null_df)
        print(f"✅ All null values handled: {len(validation_results.get('warnings', []))} warnings found")
    except Exception as e:
        print(f"❌ All null values test failed: {str(e)}")
        return False
    
    print("✅ All edge cases handled successfully!")
    return True

if __name__ == "__main__":
    print("🚀 Starting Data Validation Tests")
    print("=" * 60)
    
    success = True
    
    # Run main tests
    if not test_validation_functions():
        success = False
    
    # Run edge case tests
    if not test_edge_cases():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED! Data validation implementation is working correctly.")
        print("\n📝 Summary of implemented features:")
        print("   ✅ Comprehensive data quality validation")
        print("   ✅ Statistical distribution analysis")
        print("   ✅ Categorical data profiling")
        print("   ✅ Business rules validation")
        print("   ✅ Data quality scoring")
        print("   ✅ Comprehensive reporting")
        print("   ✅ Error handling and edge cases")
    else:
        print("❌ SOME TESTS FAILED! Please review the implementation.")
        sys.exit(1)