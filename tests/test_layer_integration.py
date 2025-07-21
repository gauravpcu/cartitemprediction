#!/usr/bin/env python3
"""
Comprehensive integration test suite for Lambda layers
Tests layer dependencies, imports, and functionality across all layers
"""

import os
import sys
import unittest
import subprocess
import time
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add layer paths to Python path for testing
LAYERS_BASE = Path(__file__).parent.parent / "layers"
CORE_DATA_SCIENCE_PATH = LAYERS_BASE / "core-data-science" / "python"
ML_LIBRARIES_PATH = LAYERS_BASE / "ml-libraries" / "python"
AWS_UTILITIES_PATH = LAYERS_BASE / "aws-utilities" / "python"

# Add all layers to path
for layer_path in [CORE_DATA_SCIENCE_PATH, ML_LIBRARIES_PATH, AWS_UTILITIES_PATH]:
    if layer_path.exists():
        sys.path.insert(0, str(layer_path))


class TestLayerImports(unittest.TestCase):
    """Test that all layer dependencies can be imported successfully"""

    def test_core_data_science_imports(self):
        """Test Core Data Science Layer imports"""
        try:
            import pandas as pd
            import numpy as np
            from dateutil import parser
            from dateutil.relativedelta import relativedelta
            
            # Test basic functionality
            df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
            arr = np.array([1, 2, 3])
            date_obj = parser.parse('2023-01-01')
            
            self.assertEqual(len(df), 3)
            self.assertEqual(arr.sum(), 6)
            self.assertEqual(date_obj.year, 2023)
            
            print("✅ Core Data Science Layer imports successful")
            
        except ImportError as e:
            self.fail(f"Failed to import Core Data Science Layer dependencies: {e}")

    def test_ml_libraries_imports(self):
        """Test ML Libraries Layer imports"""
        try:
            import joblib
            import threadpoolctl
            
            # Test basic joblib functionality
            test_data = {"test": "data"}
            with tempfile.NamedTemporaryFile(delete=False, suffix='.joblib') as tmp:
                joblib.dump(test_data, tmp.name)
                loaded_data = joblib.load(tmp.name)
                os.unlink(tmp.name)
            
            self.assertEqual(loaded_data, test_data)
            print("✅ ML Libraries Layer imports successful")
            
        except ImportError as e:
            self.fail(f"Failed to import ML Libraries Layer dependencies: {e}")

    def test_aws_utilities_imports(self):
        """Test AWS Utilities Layer imports"""
        try:
            import boto3
            import botocore
            from dateutil import parser
            import jmespath
            import urllib3
            import six
            
            # Test basic boto3 functionality
            session = boto3.Session()
            self.assertIsNotNone(session)
            
            # Test client creation for required services
            required_services = ['s3', 'dynamodb', 'lambda', 'sagemaker-runtime', 'bedrock-runtime']
            for service in required_services:
                client = boto3.client(service, region_name='us-east-1')
                self.assertIsNotNone(client)
            
            print("✅ AWS Utilities Layer imports successful")
            
        except ImportError as e:
            self.fail(f"Failed to import AWS Utilities Layer dependencies: {e}")


class TestLayerSizes(unittest.TestCase):
    """Test that all layers meet size constraints"""

    def test_core_data_science_layer_size(self):
        """Test Core Data Science Layer size constraint"""
        if not CORE_DATA_SCIENCE_PATH.exists():
            self.skipTest("Core Data Science Layer not built")
        
        size_mb = self._get_directory_size(CORE_DATA_SCIENCE_PATH)
        self.assertLess(size_mb, 100, f"Core Data Science Layer ({size_mb:.1f}MB) exceeds 100MB limit")
        print(f"✅ Core Data Science Layer size: {size_mb:.1f}MB")

    def test_ml_libraries_layer_size(self):
        """Test ML Libraries Layer size constraint"""
        if not ML_LIBRARIES_PATH.exists():
            self.skipTest("ML Libraries Layer not built")
        
        size_mb = self._get_directory_size(ML_LIBRARIES_PATH)
        self.assertLess(size_mb, 105, f"ML Libraries Layer ({size_mb:.1f}MB) exceeds 105MB limit")
        print(f"✅ ML Libraries Layer size: {size_mb:.1f}MB")

    def test_aws_utilities_layer_size(self):
        """Test AWS Utilities Layer size constraint"""
        if not AWS_UTILITIES_PATH.exists():
            self.skipTest("AWS Utilities Layer not built")
        
        size_mb = self._get_directory_size(AWS_UTILITIES_PATH)
        self.assertLess(size_mb, 50, f"AWS Utilities Layer ({size_mb:.1f}MB) exceeds 50MB limit")
        print(f"✅ AWS Utilities Layer size: {size_mb:.1f}MB")

    def _get_directory_size(self, path):
        """Calculate directory size in MB"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    continue
        return total_size / (1024 * 1024)


class TestLayerFunctionality(unittest.TestCase):
    """Test layer functionality with realistic data processing scenarios"""

    def test_data_processing_pipeline(self):
        """Test complete data processing pipeline using all layers"""
        try:
            import pandas as pd
            import numpy as np
            import boto3
            from dateutil import parser
            import joblib
            
            # Create test data similar to what functions process
            test_data = {
                'CustomerID': [1, 2, 3, 1, 2],
                'FacilityID': [101, 102, 103, 101, 102],
                'ProductID': ['PROD001', 'PROD002', 'PROD003', 'PROD001', 'PROD002'],
                'OrderUnits': [10, 5, 8, 12, 7],
                'Price': [100.0, 50.0, 80.0, 100.0, 50.0],
                'CreateDate': ['2023-01-01', '2023-01-02', '2023-01-03', '2023-01-04', '2023-01-05']
            }
            
            # Test pandas processing
            df = pd.DataFrame(test_data)
            df['CreateDate'] = pd.to_datetime(df['CreateDate'])
            df['OrderValue'] = df['OrderUnits'] * df['Price']
            
            # Test numpy operations
            df['OrderUnits_normalized'] = (df['OrderUnits'] - df['OrderUnits'].mean()) / df['OrderUnits'].std()
            
            # Test aggregations
            customer_summary = df.groupby('CustomerID').agg({
                'OrderUnits': 'sum',
                'OrderValue': 'sum',
                'ProductID': 'nunique'
            }).reset_index()
            
            # Test date operations
            df['OrderYear'] = df['CreateDate'].dt.year
            df['OrderMonth'] = df['CreateDate'].dt.month
            
            # Test joblib serialization
            with tempfile.NamedTemporaryFile(delete=False, suffix='.joblib') as tmp:
                joblib.dump(customer_summary, tmp.name)
                loaded_summary = joblib.load(tmp.name)
                os.unlink(tmp.name)
            
            # Verify results
            self.assertEqual(len(df), 5)
            self.assertGreater(len(customer_summary), 0)  # Should have at least one customer
            self.assertTrue(loaded_summary.equals(customer_summary))
            
            print("✅ Data processing pipeline test successful")
            
        except Exception as e:
            self.fail(f"Data processing pipeline test failed: {e}")

    def test_aws_service_integration(self):
        """Test AWS service integration capabilities"""
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError, ClientError
            
            # Test S3 client
            s3_client = boto3.client('s3', region_name='us-east-1')
            self.assertTrue(hasattr(s3_client, 'list_buckets'))
            self.assertTrue(hasattr(s3_client, 'get_object'))
            
            # Test DynamoDB resource
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            self.assertTrue(hasattr(dynamodb, 'Table'))
            
            # Test Lambda client
            lambda_client = boto3.client('lambda', region_name='us-east-1')
            self.assertTrue(hasattr(lambda_client, 'invoke'))
            
            # Test SageMaker Runtime client
            sagemaker_client = boto3.client('sagemaker-runtime', region_name='us-east-1')
            self.assertTrue(hasattr(sagemaker_client, 'invoke_endpoint'))
            
            # Test Bedrock Runtime client
            bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
            self.assertTrue(hasattr(bedrock_client, 'invoke_model'))
            
            print("✅ AWS service integration test successful")
            
        except ImportError as e:
            self.fail(f"AWS service integration test failed: {e}")


class TestLayerPerformance(unittest.TestCase):
    """Test layer performance characteristics"""

    def test_import_performance(self):
        """Test that layer imports are reasonably fast"""
        import_times = {}
        
        # Test pandas import time
        start_time = time.time()
        import pandas as pd
        import_times['pandas'] = time.time() - start_time
        
        # Test numpy import time
        start_time = time.time()
        import numpy as np
        import_times['numpy'] = time.time() - start_time
        
        # Test boto3 import time
        start_time = time.time()
        import boto3
        import_times['boto3'] = time.time() - start_time
        
        # Test joblib import time
        start_time = time.time()
        import joblib
        import_times['joblib'] = time.time() - start_time
        
        # Verify import times are reasonable (under 2 seconds each)
        for library, import_time in import_times.items():
            self.assertLess(import_time, 2.0, f"{library} import took {import_time:.2f}s, should be under 2s")
            print(f"✅ {library} import time: {import_time:.3f}s")

    def test_memory_usage(self):
        """Test memory usage of layer imports"""
        try:
            import psutil
            import os
            
            # Get initial memory usage
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Import all layer dependencies
            import pandas as pd
            import numpy as np
            import boto3
            import joblib
            
            # Get memory usage after imports
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            # Memory increase should be reasonable (under 200MB for all imports)
            self.assertLess(memory_increase, 200, f"Memory increase ({memory_increase:.1f}MB) is too high")
            print(f"✅ Memory usage increase: {memory_increase:.1f}MB")
            
        except ImportError:
            self.skipTest("psutil not available for memory testing")


class TestLayerCompatibility(unittest.TestCase):
    """Test layer compatibility and version consistency"""

    def test_python_version_compatibility(self):
        """Test that layers work with current Python version"""
        import sys
        
        # Verify Python version is compatible
        python_version = sys.version_info
        self.assertGreaterEqual(python_version.major, 3)
        self.assertGreaterEqual(python_version.minor, 9)
        
        print(f"✅ Python version compatibility: {python_version.major}.{python_version.minor}")

    def test_package_version_consistency(self):
        """Test that package versions are consistent and compatible"""
        try:
            import pandas as pd
            import numpy as np
            import boto3
            import joblib
            
            # Check that pandas and numpy versions are compatible
            pandas_version = pd.__version__
            numpy_version = np.__version__
            boto3_version = boto3.__version__
            joblib_version = joblib.__version__
            
            print(f"✅ Package versions:")
            print(f"   pandas: {pandas_version}")
            print(f"   numpy: {numpy_version}")
            print(f"   boto3: {boto3_version}")
            print(f"   joblib: {joblib_version}")
            
            # Verify versions are not too old
            self.assertGreater(pandas_version, "1.0.0")
            self.assertGreater(numpy_version, "1.20.0")
            self.assertGreater(boto3_version, "1.20.0")
            
        except Exception as e:
            self.fail(f"Package version consistency test failed: {e}")


def run_comprehensive_layer_tests():
    """Run all layer tests with detailed reporting"""
    print("🧪 Running Comprehensive Layer Integration Tests")
    print("=" * 60)
    
    # Create test suite
    test_classes = [
        TestLayerImports,
        TestLayerSizes,
        TestLayerFunctionality,
        TestLayerPerformance,
        TestLayerCompatibility
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
    print("📊 Test Summary:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("✅ All layer integration tests passed!")
        return True
    else:
        print("❌ Some layer integration tests failed!")
        
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
    success = run_comprehensive_layer_tests()
    sys.exit(0 if success else 1)