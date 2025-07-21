#!/usr/bin/env python3
"""
Post-Deployment Validation Tests
Comprehensive validation tests that run after deployment to verify functionality
"""

import os
import sys
import json
import time
import boto3
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import argparse


@dataclass
class ValidationResult:
    """Data class for validation results"""
    test_name: str
    component: str
    status: str  # 'pass', 'fail', 'skip'
    duration_seconds: float
    details: Dict[str, Any]
    error_message: Optional[str] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class PostDeploymentValidator:
    """Comprehensive post-deployment validation"""
    
    def __init__(self, aws_region: str = 'us-east-1', stack_name: str = None):
        self.aws_region = aws_region
        self.stack_name = stack_name
        self.results: List[ValidationResult] = []
        
        # Initialize AWS clients
        try:
            self.lambda_client = boto3.client('lambda', region_name=aws_region)
            self.cloudformation = boto3.client('cloudformation', region_name=aws_region)
            self.s3_client = boto3.client('s3', region_name=aws_region)
            self.dynamodb = boto3.client('dynamodb', region_name=aws_region)
        except Exception as e:
            print(f"Warning: Failed to initialize AWS clients: {e}")
            self.lambda_client = None
            self.cloudformation = None
            self.s3_client = None
            self.dynamodb = None
    
    def log_result(self, test_name: str, component: str, status: str, 
                   duration: float, details: Dict[str, Any], 
                   error_message: Optional[str] = None):
        """Log a validation result"""
        result = ValidationResult(
            test_name=test_name,
            component=component,
            status=status,
            duration_seconds=duration,
            details=details,
            error_message=error_message
        )
        
        self.results.append(result)
        
        # Print result
        status_symbol = "✓" if status == "pass" else "✗" if status == "fail" else "⚠"
        print(f"{status_symbol} {test_name} ({component}): {status.upper()} ({duration:.2f}s)")
        if error_message:
            print(f"  Error: {error_message}")
    
    def get_stack_outputs(self) -> Dict[str, str]:
        """Get CloudFormation stack outputs"""
        if not self.cloudformation or not self.stack_name:
            return {}
        
        try:
            response = self.cloudformation.describe_stacks(StackName=self.stack_name)
            stack = response['Stacks'][0]
            
            outputs = {}
            for output in stack.get('Outputs', []):
                outputs[output['OutputKey']] = output['OutputValue']
            
            return outputs
        except Exception as e:
            print(f"Warning: Failed to get stack outputs: {e}")
            return {}
    
    def test_lambda_function_exists(self, function_name: str) -> bool:
        """Test if Lambda function exists and is active"""
        if not self.lambda_client:
            self.log_result("function_exists", function_name, "skip", 0.0, 
                          {"reason": "Lambda client not available"})
            return False
        
        start_time = time.time()
        
        try:
            response = self.lambda_client.get_function(FunctionName=function_name)
            duration = time.time() - start_time
            
            state = response['Configuration']['State']
            details = {
                'state': state,
                'runtime': response['Configuration']['Runtime'],
                'memory_size': response['Configuration']['MemorySize'],
                'timeout': response['Configuration']['Timeout'],
                'code_size': response['Configuration']['CodeSize']
            }
            
            if state == 'Active':
                self.log_result("function_exists", function_name, "pass", duration, details)
                return True
            else:
                self.log_result("function_exists", function_name, "fail", duration, details,
                              f"Function state is {state}, expected Active")
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_result("function_exists", function_name, "fail", duration, {}, str(e))
            return False
    
    def test_lambda_function_invocation(self, function_name: str, 
                                      test_payload: Dict[str, Any] = None) -> bool:
        """Test Lambda function invocation"""
        if not self.lambda_client:
            self.log_result("function_invocation", function_name, "skip", 0.0,
                          {"reason": "Lambda client not available"})
            return False
        
        start_time = time.time()
        
        try:
            payload = test_payload or {}
            
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            duration = time.time() - start_time
            
            status_code = response['StatusCode']
            
            # Read response payload
            response_payload = {}
            if 'Payload' in response:
                try:
                    response_payload = json.loads(response['Payload'].read())
                except Exception:
                    response_payload = {"raw_response": str(response['Payload'].read())}
            
            details = {
                'status_code': status_code,
                'response_payload': response_payload,
                'function_error': response.get('FunctionError'),
                'log_result': response.get('LogResult')
            }
            
            if status_code == 200 and not response.get('FunctionError'):
                self.log_result("function_invocation", function_name, "pass", duration, details)
                return True
            else:
                error_msg = f"Status: {status_code}, Error: {response.get('FunctionError', 'Unknown')}"
                self.log_result("function_invocation", function_name, "fail", duration, details, error_msg)
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_result("function_invocation", function_name, "fail", duration, {}, str(e))
            return False
    
    def test_layer_availability(self, layer_name: str, function_name: str) -> bool:
        """Test if layer is properly attached to function"""
        if not self.lambda_client:
            self.log_result("layer_availability", layer_name, "skip", 0.0,
                          {"reason": "Lambda client not available"})
            return False
        
        start_time = time.time()
        
        try:
            response = self.lambda_client.get_function_configuration(FunctionName=function_name)
            duration = time.time() - start_time
            
            layers = response.get('Layers', [])
            layer_arns = [layer['Arn'] for layer in layers]
            
            # Check if layer name is in any of the ARNs
            layer_found = any(layer_name in arn for arn in layer_arns)
            
            details = {
                'function_name': function_name,
                'attached_layers': layer_arns,
                'looking_for': layer_name
            }
            
            if layer_found:
                self.log_result("layer_availability", layer_name, "pass", duration, details)
                return True
            else:
                self.log_result("layer_availability", layer_name, "fail", duration, details,
                              f"Layer {layer_name} not found in function {function_name}")
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_result("layer_availability", layer_name, "fail", duration, {}, str(e))
            return False
    
    def test_api_endpoint(self, endpoint_url: str, method: str = 'GET', 
                         payload: Dict[str, Any] = None) -> bool:
        """Test API Gateway endpoint"""
        start_time = time.time()
        
        try:
            if method.upper() == 'GET':
                response = requests.get(endpoint_url, timeout=30)
            elif method.upper() == 'POST':
                response = requests.post(endpoint_url, json=payload or {}, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            duration = time.time() - start_time
            
            details = {
                'url': endpoint_url,
                'method': method,
                'status_code': response.status_code,
                'response_size': len(response.content),
                'headers': dict(response.headers)
            }
            
            # Try to parse JSON response
            try:
                details['response_json'] = response.json()
            except Exception:
                details['response_text'] = response.text[:500]  # First 500 chars
            
            if 200 <= response.status_code < 300:
                self.log_result("api_endpoint", endpoint_url, "pass", duration, details)
                return True
            else:
                self.log_result("api_endpoint", endpoint_url, "fail", duration, details,
                              f"HTTP {response.status_code}: {response.reason}")
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_result("api_endpoint", endpoint_url, "fail", duration, {}, str(e))
            return False
    
    def test_s3_bucket_access(self, bucket_name: str) -> bool:
        """Test S3 bucket access"""
        if not self.s3_client:
            self.log_result("s3_bucket_access", bucket_name, "skip", 0.0,
                          {"reason": "S3 client not available"})
            return False
        
        start_time = time.time()
        
        try:
            # Test bucket exists and is accessible
            response = self.s3_client.head_bucket(Bucket=bucket_name)
            duration = time.time() - start_time
            
            details = {
                'bucket_name': bucket_name,
                'region': response.get('ResponseMetadata', {}).get('HTTPHeaders', {}).get('x-amz-bucket-region')
            }
            
            self.log_result("s3_bucket_access", bucket_name, "pass", duration, details)
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_result("s3_bucket_access", bucket_name, "fail", duration, {}, str(e))
            return False
    
    def test_dynamodb_table_access(self, table_name: str) -> bool:
        """Test DynamoDB table access"""
        if not self.dynamodb:
            self.log_result("dynamodb_table_access", table_name, "skip", 0.0,
                          {"reason": "DynamoDB client not available"})
            return False
        
        start_time = time.time()
        
        try:
            response = self.dynamodb.describe_table(TableName=table_name)
            duration = time.time() - start_time
            
            table_status = response['Table']['TableStatus']
            
            details = {
                'table_name': table_name,
                'table_status': table_status,
                'item_count': response['Table'].get('ItemCount', 0),
                'table_size_bytes': response['Table'].get('TableSizeBytes', 0)
            }
            
            if table_status == 'ACTIVE':
                self.log_result("dynamodb_table_access", table_name, "pass", duration, details)
                return True
            else:
                self.log_result("dynamodb_table_access", table_name, "fail", duration, details,
                              f"Table status is {table_status}, expected ACTIVE")
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_result("dynamodb_table_access", table_name, "fail", duration, {}, str(e))
            return False
    
    def run_comprehensive_validation(self, stack_outputs: Dict[str, str] = None) -> bool:
        """Run comprehensive post-deployment validation"""
        print("Starting post-deployment validation...")
        print("=" * 50)
        
        if not stack_outputs:
            stack_outputs = self.get_stack_outputs()
        
        all_passed = True
        
        # Test Lambda functions
        functions_to_test = [
            'DataValidationFunction',
            'EnhancedFeatureEngineeringFunction', 
            'EnhancedPredictionsFunction',
            'PredictionAPIFunction',
            'ProductPredictionAPIFunction',
            'RecommendAPIFunction',
            'FeedbackAPIFunction'
        ]
        
        for function_name in functions_to_test:
            # Test function exists
            exists = self.test_lambda_function_exists(function_name)
            if not exists:
                all_passed = False
                continue
            
            # Test basic invocation (with empty payload)
            invocation_success = self.test_lambda_function_invocation(function_name, {})
            if not invocation_success:
                all_passed = False
        
        # Test layers
        layer_function_mapping = {
            'core-data-science-layer': ['DataValidationFunction', 'EnhancedFeatureEngineeringFunction', 'EnhancedPredictionsFunction'],
            'ml-libraries-layer': ['EnhancedFeatureEngineeringFunction', 'EnhancedPredictionsFunction'],
            'aws-utilities-layer': ['DataValidationFunction', 'EnhancedFeatureEngineeringFunction', 'EnhancedPredictionsFunction']
        }
        
        for layer_name, function_names in layer_function_mapping.items():
            for function_name in function_names:
                layer_success = self.test_layer_availability(layer_name, function_name)
                if not layer_success:
                    all_passed = False
        
        # Test API endpoints
        if 'ApiEndpoint' in stack_outputs:
            base_url = stack_outputs['ApiEndpoint']
            endpoints_to_test = [
                ('predict', 'GET'),
                ('predict/products', 'GET'),
                ('recommend', 'GET'),
                ('feedback', 'POST')
            ]
            
            for endpoint, method in endpoints_to_test:
                url = f"{base_url.rstrip('/')}/{endpoint}"
                api_success = self.test_api_endpoint(url, method)
                if not api_success:
                    all_passed = False
        
        # Test S3 buckets
        s3_buckets = [
            stack_outputs.get('RawDataBucketName'),
            stack_outputs.get('ProcessedDataBucketName')
        ]
        
        for bucket_name in s3_buckets:
            if bucket_name:
                s3_success = self.test_s3_bucket_access(bucket_name)
                if not s3_success:
                    all_passed = False
        
        # Test DynamoDB tables
        dynamodb_tables = [
            stack_outputs.get('ProductLookupTableName'),
            stack_outputs.get('PredictionCacheTableName')
        ]
        
        for table_name in dynamodb_tables:
            if table_name:
                dynamodb_success = self.test_dynamodb_table_access(table_name)
                if not dynamodb_success:
                    all_passed = False
        
        print("=" * 50)
        print(f"Validation complete. Overall result: {'PASS' if all_passed else 'FAIL'}")
        
        return all_passed
    
    def generate_validation_report(self) -> Dict[str, Any]:
        """Generate validation report"""
        if not self.results:
            return {'message': 'No validation results available'}
        
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.status == 'pass'])
        failed_tests = len([r for r in self.results if r.status == 'fail'])
        skipped_tests = len([r for r in self.results if r.status == 'skip'])
        
        # Group by component
        components = {}
        for result in self.results:
            if result.component not in components:
                components[result.component] = []
            components[result.component].append(result)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': total_tests,
                'passed': passed_tests,
                'failed': failed_tests,
                'skipped': skipped_tests,
                'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0,
                'overall_status': 'PASS' if failed_tests == 0 else 'FAIL'
            },
            'components': {
                component: {
                    'total_tests': len(results),
                    'passed': len([r for r in results if r.status == 'pass']),
                    'failed': len([r for r in results if r.status == 'fail']),
                    'skipped': len([r for r in results if r.status == 'skip'])
                }
                for component, results in components.items()
            },
            'detailed_results': [asdict(result) for result in self.results],
            'failures': [
                {
                    'test_name': r.test_name,
                    'component': r.component,
                    'error_message': r.error_message,
                    'timestamp': r.timestamp
                }
                for r in self.results if r.status == 'fail'
            ]
        }
        
        return report
    
    def save_validation_report(self, filepath: Path):
        """Save validation report to file"""
        report = self.generate_validation_report()
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Validation report saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Post-Deployment Validation")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--stack-name", help="CloudFormation stack name")
    parser.add_argument("--output", "-o", type=Path, help="Output report file")
    parser.add_argument("--function", action="append", help="Specific function to test")
    parser.add_argument("--endpoint", help="API endpoint to test")
    
    args = parser.parse_args()
    
    # Initialize validator
    validator = PostDeploymentValidator(
        aws_region=args.region,
        stack_name=args.stack_name
    )
    
    if args.function:
        # Test specific functions
        for function_name in args.function:
            validator.test_lambda_function_exists(function_name)
            validator.test_lambda_function_invocation(function_name)
    elif args.endpoint:
        # Test specific endpoint
        validator.test_api_endpoint(args.endpoint)
    else:
        # Run comprehensive validation
        success = validator.run_comprehensive_validation()
        
        # Save report
        if args.output:
            validator.save_validation_report(args.output)
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
    
    # Generate and save report for specific tests
    if args.output:
        validator.save_validation_report(args.output)


if __name__ == "__main__":
    main()