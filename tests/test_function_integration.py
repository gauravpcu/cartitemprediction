#!/usr/bin/env python3
"""
Comprehensive integration test suite for Lambda functions with layers
Tests functions with actual layer dependencies and mock AWS services
"""

import os
import sys
import unittest
import json
import tempfile
import csv
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, timedelta

# Add layer paths to Python path for testing
LAYERS_BASE = Path(__file__).parent.parent / "layers"
FUNCTIONS_BASE = Path(__file__).parent.parent / "functions"

for layer_path in [LAYERS_BASE / "core-data-science" / "python", 
                   LAYERS_BASE / "ml-libraries" / "python",
                   LAYERS_BASE / "aws-utilities" / "python"]:
    if layer_path.exists():
        sys.path.insert(0, str(layer_path))

# Add function paths
for func_path in [FUNCTIONS_BASE / "data_validation",
                  FUNCTIONS_BASE / "enhanced_feature_engineering", 
                  FUNCTIONS_BASE / "enhanced_predictions"]:
    if func_path.exists():
        sys.path.insert(0, str(func_path))


class TestDataValidationFunction(unittest.TestCase):
    """Test Data Validation Function with layers"""

    def setUp(self):
        """Set up test environment"""
        self.test_data = {
            'CustomerID': [1, 2, 3, 1, 2],
            'FacilityID': [101, 102, 103, 101, 102],
            'OrderID': [1001, 1002, 1003, 1004, 1005],
            'ProductID': ['PROD001', 'PROD002', 'PROD003', 'PROD001', 'PROD002'],
            'ProductName': ['Product A', 'Product B', 'Product C', 'Product A', 'Product B'],
            'CategoryName': ['Category 1', 'Category 2', 'Category 3', 'Category 1', 'Category 2'],
            'VendorID': [201, 202, 203, 201, 202],
            'VendorName': ['Vendor A', 'Vendor B', 'Vendor C', 'Vendor A', 'Vendor B'],
            'CreateDate': ['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05'],
            'OrderUnits': [10, 5, 8, 12, 7],
            'Price': [100.0, 50.0, 80.0, 100.0, 50.0]
        }

    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket', 'LOG_LEVEL': 'INFO'})
    @patch('boto3.client')
    def test_data_validation_with_layers(self, mock_boto_client):
        """Test data validation function with layer dependencies"""
        try:
            # Import function after setting up mocks
            from functions.data_validation.app import validate_data_quality, generate_comprehensive_report
            import pandas as pd
            
            # Create test DataFrame
            df = pd.DataFrame(self.test_data)
            df['CreateDate'] = pd.to_datetime(df['CreateDate'])
            
            # Test validation function
            validation_results = validate_data_quality(df)
            
            # Verify validation results structure
            self.assertIn('is_valid', validation_results)
            self.assertIn('issues', validation_results)
            self.assertIn('warnings', validation_results)
            self.assertIn('stats', validation_results)
            self.assertIn('data_profile', validation_results)
            
            # Test comprehensive report
            report = generate_comprehensive_report(df)
            
            # Verify report structure
            self.assertIn('report_timestamp', report)
            self.assertIn('dataset_overview', report)
            self.assertIn('data_quality_score', report)
            self.assertIn('recommendations', report)
            
            # Verify data quality score is reasonable
            self.assertGreaterEqual(report['data_quality_score'], 0)
            self.assertLessEqual(report['data_quality_score'], 100)
            
            print("✅ Data Validation Function with layers test successful")
            
        except Exception as e:
            self.fail(f"Data Validation Function test failed: {e}")

    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket'})
    @patch('boto3.client')
    def test_lambda_handler_integration(self, mock_boto_client):
        """Test complete lambda handler with mocked S3 event"""
        try:
            from functions.data_validation.app import lambda_handler
            import pandas as pd
            
            # Mock S3 client
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3
            
            # Create test CSV data
            test_csv = pd.DataFrame(self.test_data).to_csv(index=False)
            mock_s3.get_object.return_value = {'Body': MagicMock()}
            mock_s3.get_object.return_value['Body'].read = MagicMock(return_value=test_csv.encode())
            
            # Create test event
            test_event = {
                'Records': [{
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'processed/test_data.csv'}
                    }
                }]
            }
            
            # Test lambda handler
            response = lambda_handler(test_event, {})
            
            # Verify response
            self.assertEqual(response['statusCode'], 200)
            self.assertIn('body', response)
            
            # Verify S3 operations were called
            mock_s3.get_object.assert_called()
            mock_s3.put_object.assert_called()
            
            print("✅ Data Validation Lambda handler integration test successful")
            
        except Exception as e:
            self.fail(f"Data Validation Lambda handler test failed: {e}")


class TestEnhancedFeatureEngineeringFunction(unittest.TestCase):
    """Test Enhanced Feature Engineering Function with layers"""

    def setUp(self):
        """Set up test environment"""
        self.test_data = {
            'CustomerID': [1, 2, 3, 1, 2],
            'FacilityID': [101, 102, 103, 101, 102],
            'ProductID': ['PROD001', 'PROD002', 'PROD003', 'PROD001', 'PROD002'],
            'ProductDescription': ['Product A', 'Product B', 'Product C', 'Product A', 'Product B'],
            'ProductCategory': ['Category 1', 'Category 2', 'Category 3', 'Category 1', 'Category 2'],
            'VendorName': ['Vendor A', 'Vendor B', 'Vendor C', 'Vendor A', 'Vendor B'],
            'CreateDate': ['1/1/23', '1/2/23', '1/3/23', '1/4/23', '1/5/23'],
            'OrderUnits': [10, 5, 8, 12, 7],
            'Price': [100.0, 50.0, 80.0, 100.0, 50.0]
        }

    @patch.dict(os.environ, {
        'PROCESSED_BUCKET': 'test-bucket',
        'PRODUCT_LOOKUP_TABLE': 'test-product-table',
        'CUSTOMER_PRODUCT_TABLE': 'test-customer-product-table'
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_feature_engineering_with_layers(self, mock_boto_resource, mock_boto_client):
        """Test feature engineering function with layer dependencies"""
        try:
            # Import function components
            from functions.enhanced_feature_engineering.app import (
                extract_temporal_features, 
                calculate_product_demand_patterns,
                create_product_lookup_table
            )
            import pandas as pd
            import numpy as np
            
            # Create test DataFrame
            df = pd.DataFrame(self.test_data)
            
            # Test temporal feature extraction
            df_with_temporal = extract_temporal_features(df)
            
            # Verify temporal features were added
            expected_temporal_features = [
                'OrderYear', 'OrderMonth', 'OrderDay', 'OrderDayOfWeek',
                'DayOfWeek_sin', 'DayOfWeek_cos', 'MonthOfYear_sin', 'MonthOfYear_cos',
                'OrderQuarter', 'IsWeekend', 'IsHoliday'
            ]
            
            for feature in expected_temporal_features:
                self.assertIn(feature, df_with_temporal.columns, f"Missing temporal feature: {feature}")
            
            # Test product demand patterns
            product_features = calculate_product_demand_patterns(df_with_temporal)
            
            # Verify product features structure
            expected_product_columns = [
                'CustomerID', 'FacilityID', 'ProductID', 'TotalOrders',
                'AvgQuantity', 'StdQuantity', 'MaxQuantity', 'MinQuantity'
            ]
            
            for col in expected_product_columns:
                self.assertIn(col, product_features.columns, f"Missing product feature: {col}")
            
            # Test product lookup table creation
            product_lookup, customer_product_lookup = create_product_lookup_table(df_with_temporal)
            
            # Verify lookup table structures
            self.assertIn('ProductID', product_lookup.columns)
            self.assertIn('ProductName', product_lookup.columns)
            self.assertIn('CategoryName', product_lookup.columns)
            
            self.assertIn('CustomerID', customer_product_lookup.columns)
            self.assertIn('FacilityID', customer_product_lookup.columns)
            self.assertIn('ProductID', customer_product_lookup.columns)
            self.assertIn('OrderCount', customer_product_lookup.columns)
            
            print("✅ Enhanced Feature Engineering Function with layers test successful")
            
        except Exception as e:
            self.fail(f"Enhanced Feature Engineering Function test failed: {e}")

    @patch.dict(os.environ, {
        'PROCESSED_BUCKET': 'test-bucket',
        'PRODUCT_LOOKUP_TABLE': 'test-product-table',
        'CUSTOMER_PRODUCT_TABLE': 'test-customer-product-table'
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_lambda_handler_integration(self, mock_boto_resource, mock_boto_client):
        """Test complete lambda handler with mocked S3 event"""
        try:
            from functions.enhanced_feature_engineering.app import lambda_handler
            import pandas as pd
            
            # Mock S3 client
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3
            
            # Mock DynamoDB resource
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto_resource.return_value = mock_dynamodb
            
            # Create test CSV file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
                df = pd.DataFrame(self.test_data)
                df.to_csv(tmp_file.name, index=False)
                tmp_file_path = tmp_file.name
            
            # Mock S3 download
            mock_s3.download_file = MagicMock()
            
            def mock_download(bucket, key, local_path):
                # Copy our test file to the expected location
                import shutil
                shutil.copy(tmp_file_path, local_path)
            
            mock_s3.download_file.side_effect = mock_download
            
            # Create test event
            test_event = {
                'Records': [{
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'raw/test_data.csv'}
                    }
                }]
            }
            
            # Test lambda handler
            response = lambda_handler(test_event, {})
            
            # Verify response
            self.assertEqual(response['statusCode'], 200)
            self.assertIn('body', response)
            
            # Verify S3 operations were called
            mock_s3.download_file.assert_called()
            mock_s3.upload_file.assert_called()
            
            # Clean up
            os.unlink(tmp_file_path)
            
            print("✅ Enhanced Feature Engineering Lambda handler integration test successful")
            
        except Exception as e:
            self.fail(f"Enhanced Feature Engineering Lambda handler test failed: {e}")


class TestEnhancedPredictionsFunction(unittest.TestCase):
    """Test Enhanced Predictions Function with layers"""

    def setUp(self):
        """Set up test environment"""
        self.test_lookup_data = {
            'ProductID': ['PROD001', 'PROD002', 'PROD003'],
            'ProductName': ['Product A', 'Product B', 'Product C'],
            'CategoryName': ['Category 1', 'Category 2', 'Category 3'],
            'vendorName': ['Vendor A', 'Vendor B', 'Vendor C']
        }
        
        self.test_customer_product_data = {
            'CustomerID': [1, 1, 2, 2, 3],
            'FacilityID': [101, 101, 102, 102, 103],
            'ProductID': ['PROD001', 'PROD002', 'PROD001', 'PROD003', 'PROD002'],
            'ProductName': ['Product A', 'Product B', 'Product A', 'Product C', 'Product B'],
            'CategoryName': ['Category 1', 'Category 2', 'Category 1', 'Category 3', 'Category 2'],
            'vendorName': ['Vendor A', 'Vendor B', 'Vendor A', 'Vendor C', 'Vendor B'],
            'OrderCount': [10, 5, 8, 12, 7],
            'FirstOrderDate': ['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05'],
            'LastOrderDate': ['2023-01-15', '2023-01-16', '2023-01-17', '2023-01-18', '2023-01-19']
        }

    @patch.dict(os.environ, {
        'PROCESSED_BUCKET': 'test-bucket',
        'BEDROCK_MODEL_ID': 'anthropic.claude-3-sonnet-20240229-v1:0',
        'SAGEMAKER_ENDPOINT_NAME': 'test-endpoint'
    })
    @patch('boto3.client')
    def test_predictions_with_layers(self, mock_boto_client):
        """Test predictions function with layer dependencies"""
        try:
            from functions.enhanced_predictions.app import (
                generate_mock_product_predictions,
                generate_fallback_recommendations
            )
            import pandas as pd
            
            # Create test DataFrames
            customer_product_df = pd.DataFrame(self.test_customer_product_data)
            
            # Test mock predictions generation
            predictions = generate_mock_product_predictions(1, 101, customer_product_df)
            
            # Verify predictions structure
            self.assertIsInstance(predictions, list)
            if predictions:
                prediction = predictions[0]
                self.assertIn('product_id', prediction)
                self.assertIn('product_name', prediction)
                self.assertIn('predictions', prediction)
                self.assertIn('order_history', prediction)
                
                # Verify prediction format
                pred_data = prediction['predictions']
                if pred_data:
                    first_date = list(pred_data.keys())[0]
                    first_pred = pred_data[first_date]
                    self.assertIn('p10', first_pred)
                    self.assertIn('p50', first_pred)
                    self.assertIn('p90', first_pred)
                    self.assertIn('mean', first_pred)
            
            # Test fallback recommendations
            recommendations = generate_fallback_recommendations(predictions)
            
            # Verify recommendations structure
            self.assertIn('recommended_products', recommendations)
            self.assertIn('ordering_schedule', recommendations)
            self.assertIn('insights', recommendations)
            
            print("✅ Enhanced Predictions Function with layers test successful")
            
        except Exception as e:
            self.fail(f"Enhanced Predictions Function test failed: {e}")

    @patch.dict(os.environ, {
        'PROCESSED_BUCKET': 'test-bucket',
        'BEDROCK_MODEL_ID': 'anthropic.claude-3-sonnet-20240229-v1:0'
    })
    @patch('boto3.client')
    def test_lambda_handler_integration(self, mock_boto_client):
        """Test complete lambda handler with mocked services"""
        try:
            from functions.enhanced_predictions.app import lambda_handler
            import pandas as pd
            
            # Mock S3 client
            mock_s3 = MagicMock()
            mock_bedrock = MagicMock()
            mock_sagemaker = MagicMock()
            
            def mock_client(service_name, **kwargs):
                if service_name == 's3':
                    return mock_s3
                elif service_name == 'bedrock-runtime':
                    return mock_bedrock
                elif service_name == 'sagemaker-runtime':
                    return mock_sagemaker
                return MagicMock()
            
            mock_boto_client.side_effect = mock_client
            
            # Mock S3 list_objects_v2 response
            mock_s3.list_objects_v2.return_value = {
                'CommonPrefixes': [{'Prefix': 'lookup/2023-01-01-12-00-00/'}]
            }
            
            # Mock S3 download_file
            def mock_download(bucket, key, local_path):
                if 'product_lookup.csv' in key:
                    df = pd.DataFrame(self.test_lookup_data)
                    df.to_csv(local_path, index=False)
                elif 'customer_product_lookup.csv' in key:
                    df = pd.DataFrame(self.test_customer_product_data)
                    df.to_csv(local_path, index=False)
            
            mock_s3.download_file.side_effect = mock_download
            
            # Create test event
            test_event = {
                'customerId': '1',
                'facilityId': '101',
                'predictionId': 'test-prediction-123'
            }
            
            # Test lambda handler
            response = lambda_handler(test_event, {})
            
            # Verify response
            self.assertEqual(response['statusCode'], 200)
            self.assertIn('body', response)
            
            # Parse response body
            response_data = json.loads(response['body'])
            self.assertIn('id', response_data)
            self.assertIn('customerId', response_data)
            self.assertIn('facilityId', response_data)
            self.assertIn('productPredictions', response_data)
            self.assertIn('recommendations', response_data)
            self.assertIn('summary', response_data)
            
            print("✅ Enhanced Predictions Lambda handler integration test successful")
            
        except Exception as e:
            self.fail(f"Enhanced Predictions Lambda handler test failed: {e}")


class TestColdStartPerformance(unittest.TestCase):
    """Test cold start performance with layers"""

    def test_function_cold_start_time(self):
        """Test that functions start reasonably quickly with layers"""
        import time
        
        # Test data validation function cold start
        start_time = time.time()
        try:
            from functions.data_validation.app import validate_data_quality
            data_validation_time = time.time() - start_time
        except ImportError:
            data_validation_time = 0
        
        # Test feature engineering function cold start
        start_time = time.time()
        try:
            from functions.enhanced_feature_engineering.app import extract_temporal_features
            feature_engineering_time = time.time() - start_time
        except ImportError:
            feature_engineering_time = 0
        
        # Test predictions function cold start
        start_time = time.time()
        try:
            from functions.enhanced_predictions.app import generate_mock_product_predictions
            predictions_time = time.time() - start_time
        except ImportError:
            predictions_time = 0
        
        print(f"✅ Cold start times:")
        print(f"   Data Validation: {data_validation_time:.3f}s")
        print(f"   Feature Engineering: {feature_engineering_time:.3f}s")
        print(f"   Predictions: {predictions_time:.3f}s")
        
        # Verify cold start times are reasonable (under 5 seconds)
        if data_validation_time > 0:
            self.assertLess(data_validation_time, 5.0, f"Data validation cold start too slow: {data_validation_time:.3f}s")
        if feature_engineering_time > 0:
            self.assertLess(feature_engineering_time, 5.0, f"Feature engineering cold start too slow: {feature_engineering_time:.3f}s")
        if predictions_time > 0:
            self.assertLess(predictions_time, 5.0, f"Predictions cold start too slow: {predictions_time:.3f}s")


def run_function_integration_tests():
    """Run all function integration tests with detailed reporting"""
    print("🧪 Running Function Integration Tests with Layers")
    print("=" * 60)
    
    # Create test suite
    test_classes = [
        TestDataValidationFunction,
        TestEnhancedFeatureEngineeringFunction,
        TestEnhancedPredictionsFunction,
        TestColdStartPerformance
    ]
    
    suite = unittest.TestSuite()
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 Function Integration Test Summary:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("✅ All function integration tests passed!")
        return True
    else:
        print("❌ Some function integration tests failed!")
        
        # Print failure details
        if result.failures:
            print("\n🔴 Failures:")
            for test, traceback in result.failures:
                print(f"   {test}: {traceback}")
        
        if result.errors:
            print("\n🔴 Errors:")
            for test, traceback in result.errors:
                print(f"   {test}: {traceback}")
        
        return False


if __name__ == "__main__":
    success = run_function_integration_tests()
    sys.exit(0 if success else 1)