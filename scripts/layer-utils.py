#!/usr/bin/env python3
"""
Lambda Layer Packaging Utilities
Provides advanced optimization and validation functions for Lambda layers
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import argparse


class LayerOptimizer:
    """Utility class for optimizing Lambda layers"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.size_limits = {
            'core-data-science': 100,  # MB
            'ml-libraries': 105,       # MB - slightly higher for ML libraries
            'aws-utilities': 50        # MB
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log message with level"""
        if self.verbose or level in ["ERROR", "WARN"]:
            print(f"[{level}] {message}")
    
    def get_directory_size(self, path: Path) -> float:
        """Get directory size in MB"""
        if not path.exists():
            return 0.0
        
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    continue
        
        return total_size / (1024 * 1024)  # Convert to MB
    
    def remove_unnecessary_files(self, layer_path: Path) -> int:
        """Remove unnecessary files and return count of removed files"""
        removed_count = 0
        
        # File patterns to remove
        file_patterns = [
            "*.pyc", "*.pyo", "*.pyd",
            "*.md", "*.rst", "*.txt",
            "*.c", "*.h", "*.cpp", "*.hpp",
            "*.pyx", "*.pxd", "*.pxi"
        ]
        
        # Directory patterns to remove
        dir_patterns = [
            "__pycache__", "*.dist-info", "*.egg-info",
            "tests", "test", "testing",
            "docs", "doc", "documentation",
            "examples", "example", "samples",
            "benchmarks", "benchmark"
        ]
        
        # Remove files by pattern
        for pattern in file_patterns:
            for file_path in layer_path.rglob(pattern):
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        removed_count += 1
                        self.log(f"Removed file: {file_path}")
                    except OSError as e:
                        self.log(f"Failed to remove file {file_path}: {e}", "WARN")
        
        # Remove directories by pattern (but preserve botocore/docs and boto3/docs)
        for pattern in dir_patterns:
            for dir_path in layer_path.rglob(pattern):
                if dir_path.is_dir():
                    # Don't remove botocore/docs or boto3/docs as they're needed
                    if ("botocore" in str(dir_path) and "docs" in str(dir_path)) or \
                       ("boto3" in str(dir_path) and "docs" in str(dir_path)):
                        continue
                    try:
                        shutil.rmtree(dir_path)
                        removed_count += 1
                        self.log(f"Removed directory: {dir_path}")
                    except OSError as e:
                        self.log(f"Failed to remove directory {dir_path}: {e}", "WARN")
        
        return removed_count
    
    def optimize_python_packages(self, layer_path: Path) -> Dict[str, int]:
        """Optimize Python packages in the layer"""
        optimization_stats = {
            'files_removed': 0,
            'dirs_removed': 0,
            'size_saved_mb': 0
        }
        
        initial_size = self.get_directory_size(layer_path)
        
        # Remove unnecessary files
        optimization_stats['files_removed'] = self.remove_unnecessary_files(layer_path)
        
        # Optimize specific packages
        self._optimize_pandas(layer_path)
        self._optimize_numpy(layer_path)
        self._optimize_sklearn(layer_path)
        self._optimize_scipy(layer_path)
        self._optimize_boto3(layer_path)
        
        final_size = self.get_directory_size(layer_path)
        optimization_stats['size_saved_mb'] = round(initial_size - final_size, 2)
        
        return optimization_stats
    
    def _optimize_pandas(self, layer_path: Path):
        """Optimize pandas package"""
        pandas_path = layer_path / "pandas"
        if not pandas_path.exists():
            return
        
        # Remove pandas test data and documentation
        test_dirs = ["tests", "io/tests", "plotting/tests"]
        for test_dir in test_dirs:
            test_path = pandas_path / test_dir
            if test_path.exists():
                shutil.rmtree(test_path)
                self.log(f"Removed pandas test directory: {test_path}")
    
    def _optimize_numpy(self, layer_path: Path):
        """Optimize numpy package"""
        numpy_path = layer_path / "numpy"
        if not numpy_path.exists():
            return
        
        # Remove numpy tests and documentation
        test_dirs = ["tests", "doc", "f2py/tests", "distutils/tests"]
        for test_dir in test_dirs:
            test_path = numpy_path / test_dir
            if test_path.exists():
                shutil.rmtree(test_path)
                self.log(f"Removed numpy test directory: {test_path}")
    
    def _optimize_sklearn(self, layer_path: Path):
        """Optimize scikit-learn package"""
        sklearn_path = layer_path / "sklearn"
        if not sklearn_path.exists():
            return
        
        # Remove sklearn tests and datasets
        test_dirs = ["tests", "datasets/tests"]
        for test_dir in test_dirs:
            test_path = sklearn_path / test_dir
            if test_path.exists():
                shutil.rmtree(test_path)
                self.log(f"Removed sklearn test directory: {test_path}")
        
        # Remove large sample datasets
        datasets_path = sklearn_path / "datasets" / "data"
        if datasets_path.exists():
            for data_file in datasets_path.glob("*.csv"):
                if data_file.stat().st_size > 1024 * 1024:  # > 1MB
                    data_file.unlink()
                    self.log(f"Removed large dataset: {data_file}")
        
        # Remove entire datasets directory to save more space
        datasets_full_path = sklearn_path / "datasets"
        if datasets_full_path.exists():
            shutil.rmtree(datasets_full_path)
            self.log(f"Removed sklearn datasets directory: {datasets_full_path}")
        
        # Remove less commonly used modules to save space
        modules_to_remove = [
            "datasets",  # Already removed above, but just in case
            "externals/_arff.py",  # ARFF file support
            "externals/_packaging",  # Packaging utilities
            "experimental",  # Experimental features
            "gaussian_process",  # Gaussian processes (less commonly used)
            "semi_supervised",  # Semi-supervised learning (less commonly used)
        ]
        
        for module in modules_to_remove:
            module_path = sklearn_path / module
            if module_path.exists():
                if module_path.is_dir():
                    shutil.rmtree(module_path)
                else:
                    module_path.unlink()
                self.log(f"Removed sklearn module: {module_path}")
    
    def _optimize_scipy(self, layer_path: Path):
        """Optimize scipy package"""
        scipy_path = layer_path / "scipy"
        if not scipy_path.exists():
            return
        
        # Remove scipy tests and documentation
        test_dirs = ["tests"]
        for test_dir in test_dirs:
            test_path = scipy_path / test_dir
            if test_path.exists():
                shutil.rmtree(test_path)
                self.log(f"Removed scipy test directory: {test_path}")
        
        # Remove less commonly used scipy modules to save significant space
        # Keep only the most essential modules for ML workloads
        essential_modules = {
            'linalg',      # Linear algebra - essential for sklearn
            'sparse',      # Sparse matrices - essential for sklearn
            'special',     # Special functions - used by sklearn
            'stats',       # Statistics - commonly used in ML
            '_lib',        # Internal utilities - required
        }
        
        # Remove non-essential modules
        for item in scipy_path.iterdir():
            if item.is_dir() and item.name not in essential_modules and not item.name.startswith('_'):
                try:
                    shutil.rmtree(item)
                    self.log(f"Removed scipy module: {item}")
                except OSError as e:
                    self.log(f"Failed to remove scipy module {item}: {e}", "WARN")
    
    def _optimize_boto3(self, layer_path: Path):
        """Optimize boto3 package"""
        boto3_path = layer_path / "boto3"
        botocore_path = layer_path / "botocore"
        
        # Remove boto3 examples but keep docs (needed for imports)
        if boto3_path.exists():
            for remove_dir in ["examples"]:  # Keep docs directory
                dir_path = boto3_path / remove_dir
                if dir_path.exists():
                    shutil.rmtree(dir_path)
                    self.log(f"Removed boto3 directory: {dir_path}")
        
        # Remove botocore data for unused services (keep only essential ones)
        if botocore_path.exists():
            data_path = botocore_path / "data"
            if data_path.exists():
                essential_services = {
                    's3', 'lambda', 'dynamodb', 'sts', 'iam', 
                    'cloudformation', 'logs', 'events'
                }
                
                for service_dir in data_path.iterdir():
                    if service_dir.is_dir() and service_dir.name not in essential_services:
                        shutil.rmtree(service_dir)
                        self.log(f"Removed unused AWS service data: {service_dir}")
            
            # Don't remove docs directory as it's needed by boto3
            # docs_path = botocore_path / "docs"
            # if docs_path.exists():
            #     shutil.rmtree(docs_path)
            #     self.log(f"Removed botocore docs directory: {docs_path}")
    
    def validate_layer_size(self, layer_name: str, layer_path: Path) -> bool:
        """Validate that layer size is within limits"""
        size_mb = self.get_directory_size(layer_path)
        limit_mb = self.size_limits.get(layer_name, 100)
        
        self.log(f"Layer '{layer_name}' size: {size_mb:.2f}MB (limit: {limit_mb}MB)")
        
        if size_mb > limit_mb:
            self.log(f"Layer '{layer_name}' exceeds size limit!", "ERROR")
            return False
        
        return True
    
    def validate_layer_imports(self, layer_name: str, layer_path: Path) -> bool:
        """Validate that required packages can be imported from the layer"""
        python_path = layer_path
        
        # Define required imports for each layer
        required_imports = {
            'core-data-science': ['pandas', 'numpy', 'dateutil'],
            'ml-libraries': ['joblib'],  # sklearn requires numpy from core-data-science layer
            'aws-utilities': ['boto3', 'botocore']
        }
        
        imports = required_imports.get(layer_name, [])
        if not imports:
            return True
        
        # For ml-libraries, also test sklearn with numpy available
        additional_test = ""
        if layer_name == 'ml-libraries':
            # Add core-data-science layer to path for sklearn testing
            core_ds_path = Path("layers/core-data-science/python")
            if core_ds_path.exists():
                additional_test = f"""
# Test sklearn with numpy available
sys.path.insert(0, '{core_ds_path}')
try:
    import sklearn
    print("✓ Successfully imported sklearn (with numpy dependency)")
except ImportError as e:
    print(f"✗ Failed to import sklearn: {{e}}")
    failed_imports.append('sklearn')
"""
        
        # Test imports in a separate directory to avoid conflicts
        import tempfile
        import os
        
        test_script = f"""
import sys
import os
# Change to temp directory to avoid numpy source conflicts
os.chdir('/tmp')
sys.path.insert(0, '{python_path}')

failed_imports = []
for module in {imports}:
    try:
        __import__(module)
        print(f"✓ Successfully imported {{module}}")
    except ImportError as e:
        print(f"✗ Failed to import {{module}}: {{e}}")
        failed_imports.append(module)

{additional_test}

if failed_imports:
    print(f"Failed imports: {{failed_imports}}")
    sys.exit(1)
else:
    print("All imports successful!")
    sys.exit(0)
"""
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", test_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.log(f"Import validation passed for layer: {layer_name}")
                return True
            else:
                self.log(f"Import validation failed for layer: {layer_name}", "ERROR")
                self.log(f"Error output: {result.stderr}", "ERROR")
                return False
                
        except subprocess.TimeoutExpired:
            self.log(f"Import validation timed out for layer: {layer_name}", "ERROR")
            return False
        except Exception as e:
            self.log(f"Import validation error for layer: {layer_name}: {e}", "ERROR")
            return False
    
    def generate_layer_report(self, layer_name: str, layer_path: Path) -> Dict:
        """Generate a comprehensive report for a layer"""
        report = {
            'layer_name': layer_name,
            'size_mb': round(self.get_directory_size(layer_path), 2),
            'size_limit_mb': self.size_limits.get(layer_name, 100),
            'within_size_limit': False,
            'import_validation': False,
            'packages': []
        }
        
        # Check size limit
        report['within_size_limit'] = report['size_mb'] <= report['size_limit_mb']
        
        # Validate imports
        report['import_validation'] = self.validate_layer_imports(layer_name, layer_path)
        
        # List packages
        for item in layer_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                package_size = round(self.get_directory_size(item), 2)
                report['packages'].append({
                    'name': item.name,
                    'size_mb': package_size
                })
        
        # Sort packages by size
        report['packages'].sort(key=lambda x: x['size_mb'], reverse=True)
        
        return report


def main():
    parser = argparse.ArgumentParser(description="Lambda Layer Packaging Utilities")
    parser.add_argument("command", choices=["optimize", "validate", "report"], 
                       help="Command to execute")
    parser.add_argument("--layer", required=True, 
                       help="Layer name (core-data-science, ml-libraries, aws-utilities)")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose output")
    
    args = parser.parse_args()
    
    optimizer = LayerOptimizer(verbose=args.verbose)
    layer_path = Path(f"layers/{args.layer}/python")
    
    if not layer_path.exists():
        print(f"ERROR: Layer path does not exist: {layer_path}")
        sys.exit(1)
    
    if args.command == "optimize":
        print(f"Optimizing layer: {args.layer}")
        stats = optimizer.optimize_python_packages(layer_path)
        print(f"Optimization complete:")
        print(f"  Files removed: {stats['files_removed']}")
        print(f"  Size saved: {stats['size_saved_mb']}MB")
        
    elif args.command == "validate":
        print(f"Validating layer: {args.layer}")
        size_valid = optimizer.validate_layer_size(args.layer, layer_path)
        import_valid = optimizer.validate_layer_imports(args.layer, layer_path)
        
        if size_valid and import_valid:
            print("✓ Layer validation passed")
            sys.exit(0)
        else:
            print("✗ Layer validation failed")
            sys.exit(1)
            
    elif args.command == "report":
        print(f"Generating report for layer: {args.layer}")
        report = optimizer.generate_layer_report(args.layer, layer_path)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()