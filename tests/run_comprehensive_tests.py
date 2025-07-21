#!/usr/bin/env python3
"""
Comprehensive test runner for Lambda optimization testing
Runs all layer and function tests with detailed reporting
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def run_test_suite(test_module, description):
    """Run a specific test suite and return results"""
    print(f"\n🧪 Running {description}")
    print("=" * 60)
    
    start_time = time.time()
    
    try:
        # Import and run the test module
        module = __import__(test_module)
        
        if hasattr(module, 'run_comprehensive_layer_tests'):
            success = module.run_comprehensive_layer_tests()
        elif hasattr(module, 'run_function_integration_tests'):
            success = module.run_function_integration_tests()
        elif hasattr(module, 'run_performance_tests'):
            success = module.run_performance_tests()
        else:
            # Run using unittest
            result = subprocess.run([
                sys.executable, '-m', 'unittest', f'{test_module}', '-v'
            ], capture_output=True, text=True, cwd=Path(__file__).parent)
            
            success = result.returncode == 0
            if not success:
                print(f"❌ {description} failed:")
                print(result.stdout)
                print(result.stderr)
            else:
                print(f"✅ {description} passed")
    
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        success = False
    
    execution_time = time.time() - start_time
    
    return {
        'success': success,
        'execution_time': execution_time,
        'description': description
    }

def check_layer_availability():
    """Check if layers are built and available"""
    layers_base = Path(__file__).parent.parent / "layers"
    
    layer_status = {}
    
    # Check Core Data Science Layer
    core_path = layers_base / "core-data-science" / "python"
    layer_status['core_data_science'] = {
        'available': core_path.exists(),
        'path': str(core_path)
    }
    
    # Check ML Libraries Layer
    ml_path = layers_base / "ml-libraries" / "python"
    layer_status['ml_libraries'] = {
        'available': ml_path.exists(),
        'path': str(ml_path)
    }
    
    # Check AWS Utilities Layer
    aws_path = layers_base / "aws-utilities" / "python"
    layer_status['aws_utilities'] = {
        'available': aws_path.exists(),
        'path': str(aws_path)
    }
    
    return layer_status

def check_function_availability():
    """Check if functions are available"""
    functions_base = Path(__file__).parent.parent / "functions"
    
    function_status = {}
    
    # Check key functions
    functions_to_check = [
        'data_validation',
        'enhanced_feature_engineering',
        'enhanced_predictions'
    ]
    
    for func_name in functions_to_check:
        func_path = functions_base / func_name / "app.py"
        function_status[func_name] = {
            'available': func_path.exists(),
            'path': str(func_path)
        }
    
    return function_status

def generate_test_report(results, layer_status, function_status):
    """Generate comprehensive test report"""
    report = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'total_test_suites': len(results),
            'passed_suites': len([r for r in results if r['success']]),
            'failed_suites': len([r for r in results if not r['success']]),
            'total_execution_time': sum(r['execution_time'] for r in results)
        },
        'layer_status': layer_status,
        'function_status': function_status,
        'test_results': results
    }
    
    return report

def print_summary_report(report):
    """Print summary report to console"""
    print("\n" + "=" * 80)
    print("📋 COMPREHENSIVE TEST SUMMARY REPORT")
    print("=" * 80)
    
    # Overall summary
    summary = report['summary']
    print(f"🕐 Test Execution Time: {summary['total_execution_time']:.2f} seconds")
    print(f"📊 Test Suites: {summary['total_test_suites']} total, {summary['passed_suites']} passed, {summary['failed_suites']} failed")
    
    # Layer status
    print(f"\n🏗️  Layer Status:")
    for layer, status in report['layer_status'].items():
        status_icon = "✅" if status['available'] else "❌"
        print(f"   {status_icon} {layer.replace('_', ' ').title()}: {'Available' if status['available'] else 'Not Built'}")
    
    # Function status
    print(f"\n⚡ Function Status:")
    for func, status in report['function_status'].items():
        status_icon = "✅" if status['available'] else "❌"
        print(f"   {status_icon} {func.replace('_', ' ').title()}: {'Available' if status['available'] else 'Not Found'}")
    
    # Test results
    print(f"\n🧪 Test Suite Results:")
    for result in report['test_results']:
        status_icon = "✅" if result['success'] else "❌"
        print(f"   {status_icon} {result['description']}: {result['execution_time']:.2f}s")
    
    # Overall status
    overall_success = summary['failed_suites'] == 0
    print(f"\n🎯 Overall Status: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    return overall_success

def save_test_report(report):
    """Save test report to file"""
    report_dir = Path(__file__).parent.parent / "reports"
    report_dir.mkdir(exist_ok=True)
    
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    report_file = report_dir / f"comprehensive-test-report-{timestamp}.json"
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Test report saved to: {report_file}")
    return report_file

def main():
    """Main test execution function"""
    print("🚀 Starting Comprehensive Lambda Optimization Tests")
    print("=" * 80)
    
    # Check prerequisites
    print("🔍 Checking Prerequisites...")
    layer_status = check_layer_availability()
    function_status = check_function_availability()
    
    # Print prerequisite status
    available_layers = sum(1 for status in layer_status.values() if status['available'])
    available_functions = sum(1 for status in function_status.values() if status['available'])
    
    print(f"   Layers available: {available_layers}/{len(layer_status)}")
    print(f"   Functions available: {available_functions}/{len(function_status)}")
    
    if available_layers == 0:
        print("⚠️  No layers found. Please build layers first using build.sh")
        return False
    
    # Define test suites to run
    test_suites = [
        ('test_layer_integration', 'Layer Integration Tests'),
        ('test_function_integration', 'Function Integration Tests'),
        ('test_performance', 'Performance Tests'),
        ('test_core_data_science_layer', 'Core Data Science Layer Tests'),
        ('test_ml_libraries_layer', 'ML Libraries Layer Tests'),
        ('test_aws_utilities_layer', 'AWS Utilities Layer Tests')
    ]
    
    # Run all test suites
    results = []
    for test_module, description in test_suites:
        result = run_test_suite(test_module, description)
        results.append(result)
    
    # Generate and display report
    report = generate_test_report(results, layer_status, function_status)
    overall_success = print_summary_report(report)
    
    # Save report
    save_test_report(report)
    
    # Return overall success status
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)