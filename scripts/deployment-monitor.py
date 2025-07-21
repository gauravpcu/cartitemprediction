#!/usr/bin/env python3
"""
Lambda Deployment Monitoring and Alerting
Provides comprehensive monitoring for Lambda deployments, layer usage, and performance
"""

import os
import sys
import json
import time
import boto3
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import argparse


@dataclass
class DeploymentEvent:
    """Data class for deployment events"""
    timestamp: str
    event_type: str  # 'build_start', 'build_complete', 'deploy_start', 'deploy_complete', 'validation'
    component: str   # layer name or function name
    status: str      # 'success', 'failure', 'in_progress'
    details: Dict[str, Any]
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None


class DeploymentMonitor:
    """Comprehensive deployment monitoring and alerting"""
    
    def __init__(self, workspace_root: Optional[Path] = None, aws_region: str = 'us-east-1'):
        self.workspace_root = workspace_root or Path.cwd()
        self.aws_region = aws_region
        self.events: List[DeploymentEvent] = []
        
        # Setup logging
        self.setup_logging()
        
        # Initialize AWS clients (optional - only if AWS credentials available)
        self.cloudwatch = None
        self.lambda_client = None
        try:
            self.cloudwatch = boto3.client('cloudwatch', region_name=aws_region)
            self.lambda_client = boto3.client('lambda', region_name=aws_region)
        except Exception as e:
            self.logger.warning(f"AWS clients not available: {e}")
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = self.workspace_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # Create logger
        self.logger = logging.getLogger('deployment_monitor')
        self.logger.setLevel(logging.INFO)
        
        # Create file handler
        log_file = log_dir / f"deployment-{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log_event(self, event_type: str, component: str, status: str, 
                  details: Dict[str, Any], duration: Optional[float] = None,
                  error_message: Optional[str] = None):
        """Log a deployment event"""
        event = DeploymentEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            component=component,
            status=status,
            details=details,
            duration_seconds=duration,
            error_message=error_message
        )
        
        self.events.append(event)
        
        # Log to file
        log_message = f"{event_type.upper()} - {component} - {status.upper()}"
        if duration:
            log_message += f" ({duration:.2f}s)"
        if error_message:
            log_message += f" - ERROR: {error_message}"
        
        if status == 'failure':
            self.logger.error(log_message)
        elif status == 'success':
            self.logger.info(log_message)
        else:
            self.logger.info(log_message)
    
    def monitor_build_process(self, component: str, build_command: List[str]) -> bool:
        """Monitor a build process and log results"""
        self.log_event('build_start', component, 'in_progress', {
            'command': ' '.join(build_command)
        })
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                build_command,
                capture_output=True,
                text=True,
                cwd=self.workspace_root
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                self.log_event('build_complete', component, 'success', {
                    'command': ' '.join(build_command),
                    'stdout': result.stdout[-1000:] if result.stdout else '',  # Last 1000 chars
                }, duration)
                return True
            else:
                self.log_event('build_complete', component, 'failure', {
                    'command': ' '.join(build_command),
                    'stdout': result.stdout[-1000:] if result.stdout else '',
                    'stderr': result.stderr[-1000:] if result.stderr else '',
                    'return_code': result.returncode
                }, duration, result.stderr)
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_event('build_complete', component, 'failure', {
                'command': ' '.join(build_command),
                'exception': str(e)
            }, duration, str(e))
            return False
    
    def validate_deployment(self, component: str, validation_type: str) -> bool:
        """Run deployment validation and log results"""
        self.log_event('validation', component, 'in_progress', {
            'validation_type': validation_type
        })
        
        start_time = time.time()
        
        try:
            if validation_type == 'size':
                success = self._validate_size(component)
            elif validation_type == 'imports':
                success = self._validate_imports(component)
            elif validation_type == 'functionality':
                success = self._validate_functionality(component)
            else:
                raise ValueError(f"Unknown validation type: {validation_type}")
            
            duration = time.time() - start_time
            
            self.log_event('validation', component, 'success' if success else 'failure', {
                'validation_type': validation_type,
                'result': success
            }, duration)
            
            return success
            
        except Exception as e:
            duration = time.time() - start_time
            self.log_event('validation', component, 'failure', {
                'validation_type': validation_type,
                'exception': str(e)
            }, duration, str(e))
            return False
    
    def _validate_size(self, component: str) -> bool:
        """Validate component size"""
        try:
            result = subprocess.run([
                'python3', 'scripts/size-validation.py', 'check',
                '--workspace', str(self.workspace_root)
            ], capture_output=True, text=True, cwd=self.workspace_root)
            
            return result.returncode == 0
        except Exception:
            return False
    
    def _validate_imports(self, component: str) -> bool:
        """Validate component imports"""
        if component.endswith('-layer'):
            layer_name = component.replace('-layer', '')
            try:
                result = subprocess.run([
                    'python3', 'scripts/layer-utils.py', 'validate',
                    '--layer', layer_name
                ], capture_output=True, text=True, cwd=self.workspace_root)
                
                return result.returncode == 0
            except Exception:
                return False
        return True  # Skip import validation for functions
    
    def _validate_functionality(self, component: str) -> bool:
        """Validate component functionality"""
        # This would run component-specific tests
        # For now, return True as a placeholder
        return True
    
    def monitor_lambda_performance(self, function_names: List[str], 
                                 time_range_minutes: int = 60) -> Dict[str, Any]:
        """Monitor Lambda function performance metrics"""
        if not self.cloudwatch:
            self.logger.warning("CloudWatch client not available for performance monitoring")
            return {}
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=time_range_minutes)
        
        performance_data = {}
        
        for function_name in function_names:
            try:
                # Get duration metrics
                duration_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Duration',
                    Dimensions=[
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,  # 5 minutes
                    Statistics=['Average', 'Maximum']
                )
                
                # Get error metrics
                error_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,
                    Statistics=['Sum']
                )
                
                # Get invocation metrics
                invocation_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Invocations',
                    Dimensions=[
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=300,
                    Statistics=['Sum']
                )
                
                performance_data[function_name] = {
                    'duration': duration_response['Datapoints'],
                    'errors': error_response['Datapoints'],
                    'invocations': invocation_response['Datapoints']
                }
                
            except Exception as e:
                self.logger.error(f"Failed to get metrics for {function_name}: {e}")
                performance_data[function_name] = {'error': str(e)}
        
        return performance_data
    
    def check_layer_usage(self) -> Dict[str, Any]:
        """Check which functions are using which layers"""
        if not self.lambda_client:
            self.logger.warning("Lambda client not available for layer usage monitoring")
            return {}
        
        layer_usage = {}
        
        try:
            # List all functions
            paginator = self.lambda_client.get_paginator('list_functions')
            
            for page in paginator.paginate():
                for function in page['Functions']:
                    function_name = function['FunctionName']
                    
                    # Get function configuration
                    try:
                        config = self.lambda_client.get_function_configuration(
                            FunctionName=function_name
                        )
                        
                        layers = config.get('Layers', [])
                        if layers:
                            layer_usage[function_name] = [
                                {
                                    'arn': layer['Arn'],
                                    'code_size': layer.get('CodeSize', 0)
                                }
                                for layer in layers
                            ]
                    
                    except Exception as e:
                        self.logger.error(f"Failed to get config for {function_name}: {e}")
        
        except Exception as e:
            self.logger.error(f"Failed to list functions: {e}")
        
        return layer_usage
    
    def generate_deployment_report(self) -> Dict[str, Any]:
        """Generate comprehensive deployment report"""
        if not self.events:
            return {'message': 'No deployment events recorded'}
        
        # Analyze events
        total_events = len(self.events)
        successful_events = len([e for e in self.events if e.status == 'success'])
        failed_events = len([e for e in self.events if e.status == 'failure'])
        
        # Group by component
        components = {}
        for event in self.events:
            if event.component not in components:
                components[event.component] = []
            components[event.component].append(event)
        
        # Calculate build times
        build_times = {}
        for component, events in components.items():
            build_events = [e for e in events if e.event_type == 'build_complete' and e.duration_seconds]
            if build_events:
                durations = [e.duration_seconds for e in build_events]
                build_times[component] = {
                    'average': sum(durations) / len(durations),
                    'max': max(durations),
                    'min': min(durations)
                }
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_events': total_events,
                'successful_events': successful_events,
                'failed_events': failed_events,
                'success_rate': (successful_events / total_events * 100) if total_events > 0 else 0
            },
            'components': {
                component: {
                    'total_events': len(events),
                    'successful_events': len([e for e in events if e.status == 'success']),
                    'failed_events': len([e for e in events if e.status == 'failure']),
                    'last_event': events[-1].timestamp if events else None
                }
                for component, events in components.items()
            },
            'build_times': build_times,
            'recent_failures': [
                {
                    'timestamp': e.timestamp,
                    'component': e.component,
                    'event_type': e.event_type,
                    'error_message': e.error_message
                }
                for e in self.events[-10:] if e.status == 'failure'
            ]
        }
        
        return report
    
    def save_deployment_report(self, filepath: Path):
        """Save deployment report to file"""
        report = self.generate_deployment_report()
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.logger.info(f"Deployment report saved to: {filepath}")
    
    def send_alert(self, alert_type: str, message: str, severity: str = 'info'):
        """Send deployment alert (placeholder for integration with alerting systems)"""
        alert_data = {
            'timestamp': datetime.now().isoformat(),
            'type': alert_type,
            'message': message,
            'severity': severity
        }
        
        # Log the alert
        if severity == 'error':
            self.logger.error(f"ALERT: {message}")
        elif severity == 'warning':
            self.logger.warning(f"ALERT: {message}")
        else:
            self.logger.info(f"ALERT: {message}")
        
        # Save alert to file for external processing
        alerts_dir = self.workspace_root / "logs" / "alerts"
        alerts_dir.mkdir(exist_ok=True)
        
        alert_file = alerts_dir / f"alert-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(alert_file, 'w') as f:
            json.dump(alert_data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Lambda Deployment Monitoring")
    parser.add_argument("command", choices=["monitor", "report", "performance", "layers"], 
                       help="Command to execute")
    parser.add_argument("--workspace", type=Path, 
                       help="Workspace root directory")
    parser.add_argument("--region", default="us-east-1",
                       help="AWS region")
    parser.add_argument("--functions", nargs="+",
                       help="Function names to monitor")
    parser.add_argument("--output", "-o", type=Path,
                       help="Output file path")
    parser.add_argument("--time-range", type=int, default=60,
                       help="Time range in minutes for performance monitoring")
    
    args = parser.parse_args()
    
    # Initialize monitor
    monitor = DeploymentMonitor(
        workspace_root=args.workspace,
        aws_region=args.region
    )
    
    if args.command == "monitor":
        # Example monitoring of build process
        if args.functions:
            for function in args.functions:
                success = monitor.monitor_build_process(
                    function,
                    ['sam', 'build', '--use-container']
                )
                if success:
                    monitor.validate_deployment(function, 'size')
                    monitor.validate_deployment(function, 'imports')
    
    elif args.command == "report":
        report = monitor.generate_deployment_report()
        if args.output:
            monitor.save_deployment_report(args.output)
        else:
            print(json.dumps(report, indent=2))
    
    elif args.command == "performance":
        if not args.functions:
            print("Error: --functions required for performance monitoring")
            sys.exit(1)
        
        performance_data = monitor.monitor_lambda_performance(
            args.functions, 
            args.time_range
        )
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(performance_data, f, indent=2)
        else:
            print(json.dumps(performance_data, indent=2))
    
    elif args.command == "layers":
        layer_usage = monitor.check_layer_usage()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(layer_usage, f, indent=2)
        else:
            print(json.dumps(layer_usage, indent=2))


if __name__ == "__main__":
    main()