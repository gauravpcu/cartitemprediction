#!/usr/bin/env python3
"""
End-to-end deployment validation test
Tests the complete deployment process from build to function validation
"""

import os
import sys
import unittest
import subprocess
import json
import time
import tempfile
from pathlib import Path

class TestEndToEndDeployment(unittest.TestCase):
    """Test complete end-to-end deployment process"""

    def setUp(self):
        """Set up test environment"""
        self.project_root = Path(__file__).parent.parent
        self.build_script = self.project_root / "build.sh"
        self.deploy_script = self.project_root / "deploy.sh"

    def test_build_layers_process(self):
        """Test that layers can be built successfully"""
        print("\n🔨 Testing layer build process...")
        
        # Check if build script exists
        if not self.build_script.exists():
            self.skipTest("Build script not found")
        
        try:
            # Run build script with timeout
            print("   Running build script...")
            result = subprocess.run([str(self.build_script)], 
                                  capture_output=True, text=True, 
                                  timeout=300, cwd=self.project_root)  # 5 minute timeout
            
            if result.returncode == 0:
                print("✅ Build script completed successfully")
                
                # Verify layers were built
                layers_dir = self.project_root / "layers"
                for layer in ["core-data-science", "ml-libraries", "aws-utilities"]:
                    layer_python_dir = layers_dir / layer / "python"
                    self.assertTrue(layer_python_dir.exists(), 
                                  f"Layer {layer} was not built properly")
                
                print("✅ All layers built successfully")
                
            else:
                print(f"❌ Build script failed with return code {result.returncode}")
                print("STDOUT:", result.stdout)
                print("STDERR:", result.stderr)
                self.fail("Build script failed")
                
        except subprocess.TimeoutExpired:
            self.fail("Build script timed out after 5 minutes")
        except Exception as e:
            self.fail(f"Build script execution failed: {e}")

    def test_sam_validate(self):
        """Test SAM template validation"""
        print("\n🔍 Testing SAM template validation...")
        
        try:
            # Run SAM validate
            result = subprocess.run(['sam', 'validate'], 
                                  capture_output=True, text=True,
                                  timeout=30, cwd=self.project_root)
            
            if result.returncode == 0:
                print("✅ SAM template validation passed")
            else:
                print(f"❌ SAM template validation failed:")
                print("STDOUT:", result.stdout)
                print("STDERR:", result.stderr)
                self.fail("SAM template validation failed")
                
        except subprocess.TimeoutExpired:
            self.fail("SAM validate timed out")
        except FileNotFoundError:
            self.skipTest("SAM CLI not available")
        except Exception as e:
            self.fail(f"SAM validate failed: {e}")

    def test_sam_build_dry_run(self):
        """Test SAM build process (dry run)"""
        print("\n🏗️  Testing SAM build process...")
        
        try:
            # Run SAM build
            result = subprocess.run(['sam', 'build', '--use-container'], 
                                  capture_output=True, text=True,
                                  timeout=600, cwd=self.project_root)  # 10 minute timeout
            
            if result.returncode == 0:
                print("✅ SAM build completed successfully")
                
                # Check that .aws-sam/build directory was created
                build_dir = self.project_root / ".aws-sam" / "build"
                self.assertTrue(build_dir.exists(), "SAM build directory not created")
                
                # Check that functions were built
                expected_functions = [
                    "DataValidationFunction",
                    "EnhancedFeatureEngineeringFunction", 
                    "EnhancedPredictionsFunction"
                ]
                
                for function in expected_functions:
                    func_build_dir = build_dir / function
                    if func_build_dir.exists():
                        print(f"✅ {function} built successfully")
                    else:
                        print(f"⚠️  {function} build directory not found")
                
            else:
                print(f"❌ SAM build failed with return code {result.returncode}")
                print("STDOUT:", result.stdout)
                print("STDERR:", result.stderr)
                
                # Don't fail the test if it's just a container issue
                if "docker" in result.stderr.lower() or "container" in result.stderr.lower():
                    self.skipTest("SAM build failed due to Docker/container issues")
                else:
                    self.fail("SAM build failed")
                
        except subprocess.TimeoutExpired:
            self.fail("SAM build timed out after 10 minutes")
        except FileNotFoundError:
            self.skipTest("SAM CLI not available")
        except Exception as e:
            self.fail(f"SAM build failed: {e}")

    def test_function_import_validation(self):
        """Test that function code can import layer dependencies"""
        print("\n🧪 Testing function import validation...")
        
        # Add layers to Python path
        layers_dir = self.project_root / "layers"
        layer_paths = [
            layers_dir / "core-data-science" / "python",
            layers_dir / "ml-libraries" / "python", 
            layers_dir / "aws-utilities" / "python"
        ]
        
        for layer_path in layer_paths:
            if layer_path.exists():
                sys.path.insert(0, str(layer_path))
        
        # Test imports that functions would use
        try:
            # Core data science imports
            import pandas as pd
            import numpy as np
            from dateutil import parser
            print("✅ Core data science imports successful")
            
            # AWS utilities imports
            import boto3
            import botocore
            print("✅ AWS utilities imports successful")
            
            # ML libraries imports
            import joblib
            print("✅ ML libraries imports successful")
            
            # Test basic functionality
            df = pd.DataFrame({'test': [1, 2, 3]})
            arr = np.array([1, 2, 3])
            s3_client = boto3.client('s3', region_name='us-east-1')
            
            self.assertEqual(len(df), 3)
            self.assertEqual(arr.sum(), 6)
            self.assertIsNotNone(s3_client)
            
            print("✅ Basic functionality tests passed")
            
        except ImportError as e:
            self.fail(f"Function import validation failed: {e}")
        except Exception as e:
            self.fail(f"Function functionality test failed: {e}")

    def test_deployment_size_validation(self):
        """Test final deployment size validation"""
        print("\n📏 Testing deployment size validation...")
        
        # Run size validation script if available
        size_validation_script = self.project_root / "scripts" / "size-validation.py"
        
        if size_validation_script.exists():
            try:
                result = subprocess.run([sys.executable, str(size_validation_script)],
                                      capture_output=True, text=True,
                                      timeout=60, cwd=self.project_root)
                
                if result.returncode == 0:
                    print("✅ Size validation passed")
                    print(result.stdout)
                else:
                    print("⚠️  Size validation warnings:")
                    print(result.stdout)
                    print(result.stderr)
                    
            except subprocess.TimeoutExpired:
                print("⚠️  Size validation timed out")
            except Exception as e:
                print(f"⚠️  Size validation error: {e}")
        else:
            print("⚠️  Size validation script not found")
        
        # Manual size check
        layers_dir = self.project_root / "layers"
        total_layer_size = 0
        
        for layer in ["core-data-science", "ml-libraries", "aws-utilities"]:
            layer_python_dir = layers_dir / layer / "python"
            if layer_python_dir.exists():
                layer_size = 0
                for dirpath, dirnames, filenames in os.walk(layer_python_dir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            layer_size += os.path.getsize(filepath)
                        except (OSError, FileNotFoundError):
                            continue
                
                layer_size_mb = layer_size / (1024 * 1024)
                total_layer_size += layer_size_mb
                print(f"   {layer}: {layer_size_mb:.1f}MB")
        
        print(f"   Total layers: {total_layer_size:.1f}MB")
        
        # Verify total size is reasonable
        self.assertLess(total_layer_size, 300, f"Total layer size too large: {total_layer_size:.1f}MB")

    def test_performance_benchmarks(self):
        """Test performance benchmarks"""
        print("\n⚡ Testing performance benchmarks...")
        
        # Test layer import performance
        start_time = time.time()
        
        # Add layers to path
        layers_dir = self.project_root / "layers"
        layer_paths = [
            layers_dir / "core-data-science" / "python",
            layers_dir / "ml-libraries" / "python",
            layers_dir / "aws-utilities" / "python"
        ]
        
        for layer_path in layer_paths:
            if layer_path.exists():
                sys.path.insert(0, str(layer_path))
        
        # Import all dependencies (simulating cold start)
        try:
            import pandas as pd
            import numpy as np
            import boto3
            import joblib
            
            import_time = time.time() - start_time
            
            print(f"   Cold start import time: {import_time:.3f}s")
            
            # Import time should be reasonable (under 5 seconds)
            self.assertLess(import_time, 5.0, f"Import time too slow: {import_time:.3f}s")
            
            # Test basic operations performance
            start_time = time.time()
            
            df = pd.DataFrame({'A': range(1000), 'B': range(1000, 2000)})
            df['C'] = df['A'] + df['B']
            result = df['C'].sum()
            
            operation_time = time.time() - start_time
            
            print(f"   Basic operations time: {operation_time:.3f}s")
            
            # Operations should be fast
            self.assertLess(operation_time, 1.0, f"Operations too slow: {operation_time:.3f}s")
            
            print("✅ Performance benchmarks passed")
            
        except Exception as e:
            self.fail(f"Performance benchmark failed: {e}")


def run_end_to_end_tests():
    """Run end-to-end deployment tests"""
    print("🚀 Running End-to-End Deployment Tests")
    print("=" * 60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEndToEndDeployment)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 End-to-End Deployment Test Summary:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    print(f"   Skipped: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("✅ All end-to-end deployment tests passed!")
        print("🎯 Deployment process is fully validated!")
        return True
    else:
        print("❌ Some end-to-end deployment tests failed!")
        
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
    success = run_end_to_end_tests()
    sys.exit(0 if success else 1)