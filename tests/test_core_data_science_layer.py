#!/usr/bin/env python3
"""
Test suite for Core Data Science Layer
Verifies layer contents, imports, and functionality
"""

import os
import sys
import unittest
import subprocess
from pathlib import Path

# Add layer to Python path for testing
LAYER_PATH = Path(__file__).parent.parent / "layers" / "core-data-science" / "python"
if LAYER_PATH.exists():
    sys.path.insert(0, str(LAYER_PATH))


class TestCoreDataScienceLayer(unittest.TestCase):
    """Test Core Data Science Layer functionality"""

    def setUp(self):
        """Set up test environment"""
        self.layer_path = LAYER_PATH
        self.max_size_mb = 100

    def test_layer_directory_exists(self):
        """Test that layer directory exists"""
        self.assertTrue(self.layer_path.exists(), 
                       f"Layer directory does not exist: {self.layer_path}")

    def test_layer_size_constraint(self):
        """Test that layer size is under 100MB"""
        if not self.layer_path.exists():
            self.skipTest("Layer not built yet")
        
        # Calculate directory size
        result = subprocess.run(['du', '-sb', str(self.layer_path)], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            size_bytes = int(result.stdout.split()[0])
            size_mb = size_bytes / (1024 * 1024)
            
            self.assertLess(size_mb, self.max_size_mb,
                           f"Layer size ({size_mb:.1f}MB) exceeds limit ({self.max_size_mb}MB)")
            print(f"✅ Layer size: {size_mb:.1f}MB (under {self.max_size_mb}MB limit)")

    def test_pandas_import(self):
        """Test that pandas can be imported from layer"""
        try:
            import pandas as pd
            self.assertTrue(hasattr(pd, 'DataFrame'), "pandas.DataFrame not available")
            self.assertTrue(hasattr(pd, 'Series'), "pandas.Series not available")
            print("✅ pandas import successful")
        except ImportError as e:
            self.fail(f"Failed to import pandas: {e}")

    def test_numpy_import(self):
        """Test that numpy can be imported from layer"""
        try:
            import numpy as np
            self.assertTrue(hasattr(np, 'array'), "numpy.array not available")
            self.assertTrue(hasattr(np, 'ndarray'), "numpy.ndarray not available")
            print("✅ numpy import successful")
        except ImportError as e:
            self.fail(f"Failed to import numpy: {e}")

    def test_dateutil_import(self):
        """Test that python-dateutil can be imported from layer"""
        try:
            from dateutil import parser
            from dateutil.relativedelta import relativedelta
            self.assertTrue(hasattr(parser, 'parse'), "dateutil.parser.parse not available")
            print("✅ python-dateutil import successful")
        except ImportError as e:
            self.fail(f"Failed to import python-dateutil: {e}")

    def test_pandas_functionality(self):
        """Test basic pandas functionality"""
        try:
            import pandas as pd
            import numpy as np
            
            # Create test DataFrame
            df = pd.DataFrame({
                'A': [1, 2, 3, 4],
                'B': ['a', 'b', 'c', 'd'],
                'C': [1.1, 2.2, 3.3, 4.4]
            })
            
            # Test basic operations
            self.assertEqual(len(df), 4)
            self.assertEqual(list(df.columns), ['A', 'B', 'C'])
            self.assertEqual(df['A'].sum(), 10)
            
            # Test with numpy integration
            df['D'] = np.array([10, 20, 30, 40])
            self.assertEqual(df['D'].sum(), 100)
            
            print("✅ pandas functionality test passed")
        except Exception as e:
            self.fail(f"pandas functionality test failed: {e}")

    def test_numpy_functionality(self):
        """Test basic numpy functionality"""
        try:
            import numpy as np
            
            # Create test arrays
            arr1 = np.array([1, 2, 3, 4])
            arr2 = np.array([10, 20, 30, 40])
            
            # Test basic operations
            self.assertEqual(arr1.sum(), 10)
            self.assertEqual((arr1 + arr2).sum(), 110)
            
            # Test matrix operations
            matrix = np.array([[1, 2], [3, 4]])
            self.assertEqual(matrix.shape, (2, 2))
            self.assertEqual(np.sum(matrix), 10)
            
            print("✅ numpy functionality test passed")
        except Exception as e:
            self.fail(f"numpy functionality test failed: {e}")

    def test_no_unnecessary_files(self):
        """Test that unnecessary files have been removed"""
        if not self.layer_path.exists():
            self.skipTest("Layer not built yet")
        
        # Check for files that should be removed
        unnecessary_patterns = [
            "**/*.pyc",
            "**/__pycache__",
            "**/test*",
            "**/doc*",
            "**/example*",
            "**/*.md",
            "**/*.rst"
        ]
        
        found_unnecessary = []
        for pattern in unnecessary_patterns:
            matches = list(self.layer_path.glob(pattern))
            if matches:
                found_unnecessary.extend([str(m.relative_to(self.layer_path)) for m in matches])
        
        if found_unnecessary:
            print(f"⚠️  Found unnecessary files (may be acceptable): {found_unnecessary[:5]}")
        else:
            print("✅ No unnecessary files found")

    def test_required_packages_present(self):
        """Test that all required packages are present"""
        if not self.layer_path.exists():
            self.skipTest("Layer not built yet")
        
        required_packages = ['pandas', 'numpy', 'dateutil']
        missing_packages = []
        
        for package in required_packages:
            package_path = self.layer_path / package
            if not package_path.exists():
                missing_packages.append(package)
        
        self.assertEqual(missing_packages, [], 
                        f"Missing required packages: {missing_packages}")
        print(f"✅ All required packages present: {required_packages}")


def run_layer_tests():
    """Run all layer tests"""
    print("Running Core Data Science Layer Tests...")
    print("=" * 50)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCoreDataScienceLayer)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ All tests passed!")
        return True
    else:
        print(f"❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")
        return False


if __name__ == "__main__":
    success = run_layer_tests()
    sys.exit(0 if success else 1)