#!/usr/bin/env python3
"""
Performance test suite for Lambda functions and layers
Measures cold start times, memory usage, and execution performance
"""

import os
import sys
import unittest
import time
import json
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add layer paths to Python path for testing
LAYERS_BASE = Path(__file__).parent.parent / "layers"
FUNCTIONS_BASE = Path(__file__).parent.parent / "functions"

for layer_path in [LAYERS_BASE / "core-data-science" / "python", 
                   LAYERS_BASE / "ml-libraries" / "python",
                   LAYERS_BASE / "aws-utilities" / "python"]:
    if layer_path.exists():
        sys.path.insert(0, str(layer_path))


class TestLayerImportPerformance(unittest.TestCase):
    """Test layer import performance"""

    def test_individual_layer_import_times(self):
        """Test import times for individual layers"""
        import_results = {}
        
        # Test Core Data Science Layer imports
        start_time = time.time()
        try:
            import pandas as pd
            import numpy as np
            from dateutil import parser
            core_time = time.time() - start_time
            import_results['core_data_science'] = {
                'time': core_time,
                'success': True,
                'components': ['pandas', 'numpy', 'dateutil']
            }
        except ImportError as e:
            import_results['core_data_science'] = {
                'time': time.time() - start_time,
                'success': False,
                'error': str(e)
            }
        
        # Test ML Libraries Layer imports
        start_time = time.time()
        try:
            import joblib
            import threadpoolctl
            ml_time = time.time() - start_time
            import_results['ml_libraries'] = {
                'time': ml_time,
                'success': True,
                'components': ['joblib', 'threadpoolctl']
            }
        except ImportError as e:
            import_results['ml_libraries'] = {
                'time': time.time() - start_time,
                'success': False,
                'error': str(e)
            }
        
        # Test AWS Utilities Layer imports
        start_time = time.time()
        try:
            import boto3
            import botocore
            aws_time = time.time() - start_time
            import_results['aws_utilities'] = {
                'time': aws_time,
                'success': True,
                'components': ['boto3', 'botocore']
            }
        except ImportError as e:
            import_results['aws_utilities'] = {
                'time': time.time() - start_time,
                'success': False,
                'error': str(e)
            }
        
        # Print results
        print("\n📊 Layer Import Performance:")
        for layer, result in import_results.items():
            if result['success']:
                print(f"   {layer}: {result['time']:.3f}s ✅")
                # Verify import time is reasonable
                self.assertLess(result['time'], 3.0, f"{layer} import too slow: {result['time']:.3f}s")
            else:
                print(f"   {layer}: FAILED - {result.get('error', 'Unknown error')} ❌")
        
        return import_results

    def test_concurrent_layer_imports(self):
        """Test performance when importing all layers together"""
        start_time = time.time()
        
        try:
            # Import all layers simultaneously
            import pandas as pd
            import numpy as np
            import boto3
            import joblib
            from dateutil import parser
            
            total_time = time.time() - start_time
            
            print(f"\n📊 Concurrent Layer Import Time: {total_time:.3f}s")
            
            # Verify total import time is reasonable
            self.assertLess(total_time, 5.0, f"Concurrent layer import too slow: {total_time:.3f}s")
            
            return total_time
            
        except ImportError as e:
            self.fail(f"Concurrent layer import failed: {e}")

    def test_memory_usage_after_imports(self):
        """Test memory usage after importing all layers"""
        try:
            import psutil
            import os
            
            # Get initial memory usage
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Import all layers
            import pandas as pd
            import numpy as np
            import boto3
            import joblib
            
            # Get memory usage after imports
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            print(f"\n📊 Memory Usage:")
            print(f"   Initial: {initial_memory:.1f}MB")
            print(f"   After imports: {final_memory:.1f}MB")
            print(f"   Increase: {memory_increase:.1f}MB")
            
            # Verify memory usage is reasonable
            self.assertLess(memory_increase, 300, f"Memory usage too high: {memory_increase:.1f}MB")
            
            return memory_increase
            
        except ImportError:
            self.skipTest("psutil not available for memory testing")


class TestFunctionColdStartPerformance(unittest.TestCase):
    """Test function cold start performance"""

    def test_data_validation_cold_start(self):
        """Test data validation function cold start performance"""
        start_time = time.time()
        
        try:
            # Import function modules
            from functions.data_validation.app import (
                validate_data_quality,
                generate_comprehensive_report,
                lambda_handler
            )
            
            cold_start_time = time.time() - start_time
            
            print(f"\n📊 Data Validation Cold Start: {cold_start_time:.3f}s")
            
            # Verify cold start time is reasonable
            self.assertLess(cold_start_time, 10.0, f"Data validation cold start too slow: {cold_start_time:.3f}s")
            
            return cold_start_time
            
        except ImportError as e:
            self.skipTest(f"Data validation function not available: {e}")

    def test_feature_engineering_cold_start(self):
        """Test feature engineering function cold start performance"""
        start_time = time.time()
        
        try:
            # Import function modules
            from functions.enhanced_feature_engineering.app import (
                extract_temporal_features,
                calculate_product_demand_patterns,
                lambda_handler
            )
            
            cold_start_time = time.time() - start_time
            
            print(f"📊 Feature Engineering Cold Start: {cold_start_time:.3f}s")
            
            # Verify cold start time is reasonable
            self.assertLess(cold_start_time, 10.0, f"Feature engineering cold start too slow: {cold_start_time:.3f}s")
            
            return cold_start_time
            
        except ImportError as e:
            self.skipTest(f"Feature engineering function not available: {e}")

    def test_predictions_cold_start(self):
        """Test predictions function cold start performance"""
        start_time = time.time()
        
        try:
            # Import function modules
            from functions.enhanced_predictions.app import (
                generate_mock_product_predictions,
                call_bedrock_for_product_recommendations,
                lambda_handler
            )
            
            cold_start_time = time.time() - start_time
            
            print(f"📊 Predictions Cold Start: {cold_start_time:.3f}s")
            
            # Verify cold start time is reasonable
            self.assertLess(cold_start_time, 10.0, f"Predictions cold start too slow: {cold_start_time:.3f}s")
            
            return cold_start_time
            
        except ImportError as e:
            self.skipTest(f"Predictions function not available: {e}")


class TestFunctionExecutionPerformance(unittest.TestCase):
    """Test function execution performance with realistic data"""

    def setUp(self):
        """Set up test data"""
        self.test_data = {
            'CustomerID': list(range(1, 101)) * 10,  # 1000 records
            'FacilityID': list(range(101, 111)) * 100,
            'ProductID': [f'PROD{i:03d}' for i in range(1, 51)] * 20,
            'ProductName': [f'Product {i}' for i in range(1, 51)] * 20,
            'CategoryName': [f'Category {i%10}' for i in range(1000)],
            'VendorName': [f'Vendor {i%20}' for i in range(1000)],
            'CreateDate': ['2023-01-01'] * 1000,
            'OrderUnits': [10] * 1000,
            'Price': [100.0] * 1000
        }

    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket'})
    @patch('boto3.client')
    def test_data_validation_execution_time(self, mock_boto_client):
        """Test data validation execution performance"""
        try:
            from functions.data_validation.app import validate_data_quality
            import pandas as pd
            
            # Create test DataFrame
            df = pd.DataFrame(self.test_data)
            df['CreateDate'] = pd.to_datetime(df['CreateDate'])
            
            # Measure execution time
            start_time = time.time()
            validation_results = validate_data_quality(df)
            execution_time = time.time() - start_time
            
            print(f"\n📊 Data Validation Execution:")
            print(f"   Records processed: {len(df)}")
            print(f"   Execution time: {execution_time:.3f}s")
            print(f"   Records per second: {len(df)/execution_time:.0f}")
            
            # Verify execution time is reasonable
            self.assertLess(execution_time, 30.0, f"Data validation execution too slow: {execution_time:.3f}s")
            self.assertIsNotNone(validation_results)
            
            return execution_time
            
        except Exception as e:
            self.fail(f"Data validation execution test failed: {e}")

    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket'})
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_feature_engineering_execution_time(self, mock_boto_resource, mock_boto_client):
        """Test feature engineering execution performance"""
        try:
            from functions.enhanced_feature_engineering.app import (
                extract_temporal_features,
                calculate_product_demand_patterns
            )
            import pandas as pd
            
            # Create test DataFrame
            df = pd.DataFrame(self.test_data)
            
            # Measure temporal feature extraction time
            start_time = time.time()
            df_with_temporal = extract_temporal_features(df)
            temporal_time = time.time() - start_time
            
            # Measure product demand patterns calculation time
            start_time = time.time()
            product_features = calculate_product_demand_patterns(df_with_temporal)
            patterns_time = time.time() - start_time
            
            total_time = temporal_time + patterns_time
            
            print(f"\n📊 Feature Engineering Execution:")
            print(f"   Records processed: {len(df)}")
            print(f"   Temporal features time: {temporal_time:.3f}s")
            print(f"   Product patterns time: {patterns_time:.3f}s")
            print(f"   Total time: {total_time:.3f}s")
            print(f"   Records per second: {len(df)/total_time:.0f}")
            
            # Verify execution time is reasonable
            self.assertLess(total_time, 60.0, f"Feature engineering execution too slow: {total_time:.3f}s")
            self.assertIsNotNone(product_features)
            
            return total_time
            
        except Exception as e:
            self.fail(f"Feature engineering execution test failed: {e}")

    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket'})
    @patch('boto3.client')
    def test_predictions_execution_time(self, mock_boto_client):
        """Test predictions execution performance"""
        try:
            from functions.enhanced_predictions.app import generate_mock_product_predictions
            import pandas as pd
            
            # Create test customer-product lookup data
            customer_product_data = {
                'CustomerID': [1] * 50,  # 50 products for one customer
                'FacilityID': [101] * 50,
                'ProductID': [f'PROD{i:03d}' for i in range(1, 51)],
                'ProductName': [f'Product {i}' for i in range(1, 51)],
                'CategoryName': [f'Category {i%10}' for i in range(50)],
                'vendorName': [f'Vendor {i%5}' for i in range(50)],
                'OrderCount': [10] * 50,
                'FirstOrderDate': ['2023-01-01'] * 50,
                'LastOrderDate': ['2023-01-15'] * 50
            }
            
            customer_product_df = pd.DataFrame(customer_product_data)
            
            # Measure prediction generation time
            start_time = time.time()
            predictions = generate_mock_product_predictions(1, 101, customer_product_df)
            execution_time = time.time() - start_time
            
            print(f"\n📊 Predictions Execution:")
            print(f"   Products processed: {len(customer_product_df)}")
            print(f"   Predictions generated: {len(predictions)}")
            print(f"   Execution time: {execution_time:.3f}s")
            if predictions:
                print(f"   Products per second: {len(predictions)/execution_time:.0f}")
            
            # Verify execution time is reasonable
            self.assertLess(execution_time, 30.0, f"Predictions execution too slow: {execution_time:.3f}s")
            self.assertIsInstance(predictions, list)
            
            return execution_time
            
        except Exception as e:
            self.fail(f"Predictions execution test failed: {e}")


class TestScalabilityPerformance(unittest.TestCase):
    """Test performance with different data sizes"""

    def test_data_validation_scalability(self):
        """Test data validation performance with different data sizes"""
        try:
            from functions.data_validation.app import validate_data_quality
            import pandas as pd
            
            sizes = [100, 500, 1000, 2000]
            results = {}
            
            for size in sizes:
                # Create test data of specified size
                test_data = {
                    'CustomerID': list(range(1, size + 1)),
                    'FacilityID': [101] * size,
                    'ProductID': [f'PROD{i%100:03d}' for i in range(size)],
                    'CreateDate': ['2023-01-01'] * size,
                    'OrderUnits': [10] * size,
                    'Price': [100.0] * size
                }
                
                df = pd.DataFrame(test_data)
                df['CreateDate'] = pd.to_datetime(df['CreateDate'])
                
                # Measure execution time
                start_time = time.time()
                validation_results = validate_data_quality(df)
                execution_time = time.time() - start_time
                
                results[size] = {
                    'time': execution_time,
                    'records_per_second': size / execution_time if execution_time > 0 else 0
                }
            
            print(f"\n📊 Data Validation Scalability:")
            for size, result in results.items():
                print(f"   {size} records: {result['time']:.3f}s ({result['records_per_second']:.0f} rec/s)")
            
            # Verify performance doesn't degrade significantly
            if len(results) >= 2:
                small_rps = results[min(sizes)]['records_per_second']
                large_rps = results[max(sizes)]['records_per_second']
                
                # Performance shouldn't degrade by more than 50%
                if small_rps > 0:
                    degradation = (small_rps - large_rps) / small_rps
                    self.assertLess(degradation, 0.5, f"Performance degradation too high: {degradation:.2%}")
            
            return results
            
        except Exception as e:
            self.fail(f"Data validation scalability test failed: {e}")


class TestMemoryUsagePerformance(unittest.TestCase):
    """Test memory usage during function execution"""

    def test_memory_usage_during_processing(self):
        """Test memory usage during data processing"""
        try:
            import psutil
            import os
            import pandas as pd
            
            process = psutil.Process(os.getpid())
            
            # Get initial memory
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Create large test dataset
            large_data = {
                'CustomerID': list(range(1, 5001)),  # 5000 records
                'FacilityID': [101] * 5000,
                'ProductID': [f'PROD{i%500:03d}' for i in range(5000)],
                'CreateDate': ['2023-01-01'] * 5000,
                'OrderUnits': [10] * 5000,
                'Price': [100.0] * 5000
            }
            
            # Create DataFrame and measure memory
            df = pd.DataFrame(large_data)
            after_df_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Process data and measure memory
            df['CreateDate'] = pd.to_datetime(df['CreateDate'])
            df['OrderValue'] = df['OrderUnits'] * df['Price']
            after_processing_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Calculate memory usage
            df_memory_increase = after_df_memory - initial_memory
            processing_memory_increase = after_processing_memory - after_df_memory
            total_memory_increase = after_processing_memory - initial_memory
            
            print(f"\n📊 Memory Usage During Processing:")
            print(f"   Initial memory: {initial_memory:.1f}MB")
            print(f"   After DataFrame creation: {after_df_memory:.1f}MB (+{df_memory_increase:.1f}MB)")
            print(f"   After processing: {after_processing_memory:.1f}MB (+{processing_memory_increase:.1f}MB)")
            print(f"   Total increase: {total_memory_increase:.1f}MB")
            
            # Verify memory usage is reasonable
            self.assertLess(total_memory_increase, 500, f"Memory usage too high: {total_memory_increase:.1f}MB")
            
            return {
                'initial': initial_memory,
                'after_df': after_df_memory,
                'after_processing': after_processing_memory,
                'total_increase': total_memory_increase
            }
            
        except ImportError:
            self.skipTest("psutil not available for memory testing")


def run_performance_tests():
    """Run all performance tests with detailed reporting"""
    print("🚀 Running Performance Tests")
    print("=" * 60)
    
    # Create test suite
    test_classes = [
        TestLayerImportPerformance,
        TestFunctionColdStartPerformance,
        TestFunctionExecutionPerformance,
        TestScalabilityPerformance,
        TestMemoryUsagePerformance
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
    print("📊 Performance Test Summary:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("✅ All performance tests passed!")
        return True
    else:
        print("❌ Some performance tests failed!")
        
        # Print failure details
        if result.failures:
            print("\n🔴 Performance Issues:")
            for test, traceback in result.failures:
                print(f"   {test}: {traceback}")
        
        if result.errors:
            print("\n🔴 Errors:")
            for test, traceback in result.errors:
                print(f"   {test}: {traceback}")
        
        return False


if __name__ == "__main__":
    success = run_performance_tests()
    sys.exit(0 if success else 1)