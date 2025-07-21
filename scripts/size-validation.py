#!/usr/bin/env python3
"""
Lambda Size Validation and Monitoring Utilities
Comprehensive size validation for Lambda functions and layers with deployment prevention
"""

import os
import sys
import json
import zipfile
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import argparse


@dataclass
class SizeReport:
    """Data class for size reporting"""
    name: str
    type: str  # 'layer' or 'function'
    size_mb: float
    size_limit_mb: float
    within_limit: bool
    compressed_size_mb: Optional[float] = None
    file_count: Optional[int] = None
    largest_files: Optional[List[Dict[str, Any]]] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class SizeValidator:
    """Comprehensive size validation for Lambda functions and layers"""
    
    # AWS Lambda size limits
    LAMBDA_LIMITS = {
        'function_unzipped': 262,      # MB - unzipped function + layers
        'function_zipped': 50,         # MB - zipped function package
        'layer_unzipped': 262,         # MB - unzipped layer
        'layer_zipped': 50,            # MB - zipped layer
        'total_layers': 5,             # Maximum number of layers per function
        'all_layers_unzipped': 262     # MB - all layers combined unzipped
    }
    
    # Custom size targets for optimization
    SIZE_TARGETS = {
        'core-data-science-layer': 100,
        'ml-libraries-layer': 105,
        'aws-utilities-layer': 50,
        'function_default': 50
    }
    
    def __init__(self, verbose: bool = False, workspace_root: Optional[Path] = None):
        self.verbose = verbose
        self.workspace_root = workspace_root or Path.cwd()
        self.reports: List[SizeReport] = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with level"""
        if self.verbose or level in ["ERROR", "WARN"]:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [{level}] {message}")
    
    def get_directory_size(self, path: Path) -> Tuple[float, int]:
        """Get directory size in MB and file count"""
        if not path.exists():
            return 0.0, 0
        
        total_size = 0
        file_count = 0
        
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                    file_count += 1
                except (OSError, FileNotFoundError):
                    continue
        
        return total_size / (1024 * 1024), file_count  # Convert to MB
    
    def get_largest_files(self, path: Path, top_n: int = 10) -> List[Dict[str, Any]]:
        """Get the largest files in a directory"""
        files = []
        
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = Path(dirpath) / filename
                try:
                    size = filepath.stat().st_size
                    files.append({
                        'path': str(filepath.relative_to(path)),
                        'size_mb': round(size / (1024 * 1024), 3),
                        'size_bytes': size
                    })
                except (OSError, FileNotFoundError):
                    continue
        
        # Sort by size and return top N
        files.sort(key=lambda x: x['size_bytes'], reverse=True)
        return files[:top_n]
    
    def create_zip_package(self, source_path: Path, output_path: Path) -> float:
        """Create a zip package and return its size in MB"""
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in source_path.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(source_path)
                    zipf.write(file_path, arcname)
        
        return output_path.stat().st_size / (1024 * 1024)
    
    def validate_layer(self, layer_name: str, layer_path: Path) -> SizeReport:
        """Validate a Lambda layer"""
        self.log(f"Validating layer: {layer_name}")
        
        # Get unzipped size
        size_mb, file_count = self.get_directory_size(layer_path)
        
        # Get size limit
        size_limit = self.SIZE_TARGETS.get(layer_name, self.LAMBDA_LIMITS['layer_unzipped'])
        
        # Get largest files
        largest_files = self.get_largest_files(layer_path)
        
        # Create temporary zip to check compressed size
        compressed_size = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                compressed_size = self.create_zip_package(layer_path, Path(tmp_file.name))
                os.unlink(tmp_file.name)
        except Exception as e:
            self.log(f"Failed to create zip for {layer_name}: {e}", "WARN")
        
        # Create report
        report = SizeReport(
            name=layer_name,
            type='layer',
            size_mb=round(size_mb, 2),
            size_limit_mb=size_limit,
            within_limit=size_mb <= size_limit,
            compressed_size_mb=round(compressed_size, 2) if compressed_size else None,
            file_count=file_count,
            largest_files=largest_files
        )
        
        self.reports.append(report)
        
        # Log results
        status = "✓ PASS" if report.within_limit else "✗ FAIL"
        self.log(f"{status} Layer '{layer_name}': {size_mb:.2f}MB / {size_limit}MB")
        if compressed_size:
            zip_status = "✓" if compressed_size <= self.LAMBDA_LIMITS['layer_zipped'] else "✗"
            self.log(f"  {zip_status} Compressed: {compressed_size:.2f}MB / {self.LAMBDA_LIMITS['layer_zipped']}MB")
        
        return report
    
    def validate_function(self, function_name: str, function_path: Path, 
                         layer_names: Optional[List[str]] = None) -> SizeReport:
        """Validate a Lambda function"""
        self.log(f"Validating function: {function_name}")
        
        # Get function size
        size_mb, file_count = self.get_directory_size(function_path)
        
        # Get size limit
        size_limit = self.SIZE_TARGETS.get(function_name, self.SIZE_TARGETS['function_default'])
        
        # Get largest files
        largest_files = self.get_largest_files(function_path)
        
        # Create temporary zip to check compressed size
        compressed_size = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                compressed_size = self.create_zip_package(function_path, Path(tmp_file.name))
                os.unlink(tmp_file.name)
        except Exception as e:
            self.log(f"Failed to create zip for {function_name}: {e}", "WARN")
        
        # Calculate total size with layers
        total_size_with_layers = size_mb
        if layer_names:
            for layer_name in layer_names:
                layer_path = self.workspace_root / "layers" / layer_name / "python"
                if layer_path.exists():
                    layer_size, _ = self.get_directory_size(layer_path)
                    total_size_with_layers += layer_size
        
        # Create report
        report = SizeReport(
            name=function_name,
            type='function',
            size_mb=round(size_mb, 2),
            size_limit_mb=size_limit,
            within_limit=size_mb <= size_limit,
            compressed_size_mb=round(compressed_size, 2) if compressed_size else None,
            file_count=file_count,
            largest_files=largest_files
        )
        
        self.reports.append(report)
        
        # Log results
        status = "✓ PASS" if report.within_limit else "✗ FAIL"
        self.log(f"{status} Function '{function_name}': {size_mb:.2f}MB / {size_limit}MB")
        if compressed_size:
            zip_status = "✓" if compressed_size <= self.LAMBDA_LIMITS['function_zipped'] else "✗"
            self.log(f"  {zip_status} Compressed: {compressed_size:.2f}MB / {self.LAMBDA_LIMITS['function_zipped']}MB")
        
        # Check total size with layers
        if layer_names:
            total_status = "✓" if total_size_with_layers <= self.LAMBDA_LIMITS['function_unzipped'] else "✗"
            self.log(f"  {total_status} Total with layers: {total_size_with_layers:.2f}MB / {self.LAMBDA_LIMITS['function_unzipped']}MB")
        
        return report
    
    def validate_all_layers(self) -> List[SizeReport]:
        """Validate all layers in the workspace"""
        layers_dir = self.workspace_root / "layers"
        layer_reports = []
        
        if not layers_dir.exists():
            self.log("No layers directory found", "WARN")
            return layer_reports
        
        for layer_dir in layers_dir.iterdir():
            if layer_dir.is_dir():
                python_dir = layer_dir / "python"
                if python_dir.exists():
                    layer_name = layer_dir.name
                    report = self.validate_layer(layer_name, python_dir)
                    layer_reports.append(report)
        
        return layer_reports
    
    def validate_all_functions(self) -> List[SizeReport]:
        """Validate all functions in the workspace"""
        functions_dir = self.workspace_root / "functions"
        function_reports = []
        
        if not functions_dir.exists():
            self.log("No functions directory found", "WARN")
            return function_reports
        
        # Function to layer mapping (from SAM template analysis)
        function_layers = {
            'data_validation': ['core-data-science', 'aws-utilities'],
            'enhanced_feature_engineering': ['core-data-science', 'ml-libraries', 'aws-utilities'],
            'enhanced_predictions': ['core-data-science', 'ml-libraries', 'aws-utilities'],
            'prediction_api': [],
            'product_prediction_api': [],
            'recommend_api': [],
            'feedback_api': []
        }
        
        for function_dir in functions_dir.iterdir():
            if function_dir.is_dir():
                function_name = function_dir.name
                layers = function_layers.get(function_name, [])
                report = self.validate_function(function_name, function_dir, layers)
                function_reports.append(report)
        
        return function_reports
    
    def check_deployment_readiness(self) -> bool:
        """Check if deployment is ready based on size validation"""
        if not self.reports:
            self.log("No validation reports available", "WARN")
            return False
        
        failed_items = [r for r in self.reports if not r.within_limit]
        
        if failed_items:
            self.log("Deployment blocked due to size violations:", "ERROR")
            for item in failed_items:
                self.log(f"  - {item.name} ({item.type}): {item.size_mb}MB > {item.size_limit_mb}MB", "ERROR")
            return False
        
        self.log("✓ All components pass size validation - deployment ready")
        return True
    
    def generate_size_report(self, output_format: str = 'json') -> str:
        """Generate comprehensive size report"""
        if not self.reports:
            return "No validation data available"
        
        # Summary statistics
        total_items = len(self.reports)
        passed_items = len([r for r in self.reports if r.within_limit])
        failed_items = total_items - passed_items
        
        layers = [r for r in self.reports if r.type == 'layer']
        functions = [r for r in self.reports if r.type == 'function']
        
        summary = {
            'validation_timestamp': datetime.now().isoformat(),
            'summary': {
                'total_items': total_items,
                'passed': passed_items,
                'failed': failed_items,
                'deployment_ready': failed_items == 0
            },
            'layers': {
                'count': len(layers),
                'total_size_mb': round(sum(l.size_mb for l in layers), 2),
                'passed': len([l for l in layers if l.within_limit])
            },
            'functions': {
                'count': len(functions),
                'total_size_mb': round(sum(f.size_mb for f in functions), 2),
                'passed': len([f for f in functions if f.within_limit])
            },
            'details': [asdict(report) for report in self.reports]
        }
        
        if output_format == 'json':
            return json.dumps(summary, indent=2)
        elif output_format == 'text':
            return self._format_text_report(summary)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
    
    def _format_text_report(self, summary: Dict) -> str:
        """Format summary as text report"""
        lines = []
        lines.append("=" * 60)
        lines.append("LAMBDA SIZE VALIDATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Timestamp: {summary['validation_timestamp']}")
        lines.append("")
        
        # Summary
        s = summary['summary']
        status = "✓ READY" if s['deployment_ready'] else "✗ BLOCKED"
        lines.append(f"Deployment Status: {status}")
        lines.append(f"Total Items: {s['total_items']} (Passed: {s['passed']}, Failed: {s['failed']})")
        lines.append("")
        
        # Layers
        l = summary['layers']
        lines.append(f"Layers: {l['count']} items, {l['total_size_mb']}MB total")
        lines.append(f"  Passed: {l['passed']}/{l['count']}")
        lines.append("")
        
        # Functions
        f = summary['functions']
        lines.append(f"Functions: {f['count']} items, {f['total_size_mb']}MB total")
        lines.append(f"  Passed: {f['passed']}/{f['count']}")
        lines.append("")
        
        # Details
        lines.append("DETAILED RESULTS:")
        lines.append("-" * 40)
        
        for detail in summary['details']:
            status = "✓" if detail['within_limit'] else "✗"
            lines.append(f"{status} {detail['name']} ({detail['type']})")
            lines.append(f"    Size: {detail['size_mb']}MB / {detail['size_limit_mb']}MB")
            if detail['compressed_size_mb']:
                lines.append(f"    Compressed: {detail['compressed_size_mb']}MB")
            lines.append(f"    Files: {detail['file_count']}")
            
            # Show largest files
            if detail['largest_files']:
                lines.append("    Largest files:")
                for file_info in detail['largest_files'][:5]:  # Top 5
                    lines.append(f"      {file_info['size_mb']}MB - {file_info['path']}")
            lines.append("")
        
        return "\n".join(lines)
    
    def save_report(self, filepath: Path, output_format: str = 'json'):
        """Save size report to file"""
        report_content = self.generate_size_report(output_format)
        
        with open(filepath, 'w') as f:
            f.write(report_content)
        
        self.log(f"Size report saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Lambda Size Validation Utilities")
    parser.add_argument("command", choices=["validate", "report", "check"], 
                       help="Command to execute")
    parser.add_argument("--target", choices=["all", "layers", "functions"], 
                       default="all", help="What to validate")
    parser.add_argument("--format", choices=["json", "text"], 
                       default="json", help="Output format")
    parser.add_argument("--output", "-o", type=Path, 
                       help="Output file path")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose output")
    parser.add_argument("--workspace", type=Path, 
                       help="Workspace root directory")
    
    args = parser.parse_args()
    
    # Initialize validator
    validator = SizeValidator(
        verbose=args.verbose,
        workspace_root=args.workspace
    )
    
    # Execute command
    if args.command == "validate":
        if args.target in ["all", "layers"]:
            validator.validate_all_layers()
        if args.target in ["all", "functions"]:
            validator.validate_all_functions()
        
        # Generate and display report
        report = validator.generate_size_report(args.format)
        if args.output:
            validator.save_report(args.output, args.format)
        else:
            print(report)
    
    elif args.command == "report":
        # Load existing reports if available, otherwise validate
        if not validator.reports:
            if args.target in ["all", "layers"]:
                validator.validate_all_layers()
            if args.target in ["all", "functions"]:
                validator.validate_all_functions()
        
        report = validator.generate_size_report(args.format)
        if args.output:
            validator.save_report(args.output, args.format)
        else:
            print(report)
    
    elif args.command == "check":
        # Validate and check deployment readiness
        if args.target in ["all", "layers"]:
            validator.validate_all_layers()
        if args.target in ["all", "functions"]:
            validator.validate_all_functions()
        
        is_ready = validator.check_deployment_readiness()
        
        if args.output:
            validator.save_report(args.output, args.format)
        
        # Exit with appropriate code
        sys.exit(0 if is_ready else 1)


if __name__ == "__main__":
    main()