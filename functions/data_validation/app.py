import json
import os
import logging
import urllib.parse
from datetime import datetime, timedelta

# Import layer dependencies with error handling
try:
    import boto3
except ImportError as e:
    logging.error(f"Failed to import boto3 from AWSUtilitiesLayer: {e}")
    raise

try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    logging.error(f"Failed to import pandas/numpy from CoreDataScienceLayer: {e}")
    raise

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

s3_client = boto3.client('s3')
processed_bucket = os.environ.get('PROCESSED_BUCKET')

def generate_data_distribution_analysis(df):
    """Generate comprehensive data distribution analysis matching notebook patterns"""
    distribution_analysis = {}
    
    # Numeric columns analysis
    numeric_columns = df.select_dtypes(include=[np.number]).columns
    for col in numeric_columns:
        if col in df.columns:
            try:
                col_data = df[col].dropna()
                if len(col_data) > 0:
                    distribution_analysis[col] = {
                        'count': len(col_data),
                        'mean': float(col_data.mean()),
                        'std': float(col_data.std()),
                        'min': float(col_data.min()),
                        'max': float(col_data.max()),
                        'median': float(col_data.median()),
                        'q25': float(col_data.quantile(0.25)),
                        'q75': float(col_data.quantile(0.75)),
                        'skewness': float(col_data.skew()),
                        'kurtosis': float(col_data.kurtosis()),
                        'zeros': int((col_data == 0).sum()),
                        'outliers_iqr': int(detect_outliers_iqr(col_data))
                    }
            except Exception as e:
                logger.warning(f"Error analyzing distribution for {col}: {str(e)}")
    
    return distribution_analysis

def detect_outliers_iqr(data):
    """Detect outliers using IQR method"""
    try:
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        return ((data < lower_bound) | (data > upper_bound)).sum()
    except:
        return 0

def analyze_categorical_distributions(df):
    """Analyze categorical column distributions matching notebook's approach"""
    categorical_analysis = {}
    
    categorical_columns = df.select_dtypes(include=['object']).columns
    for col in categorical_columns:
        if col in df.columns:
            try:
                value_counts = df[col].value_counts()
                categorical_analysis[col] = {
                    'unique_values': int(df[col].nunique()),
                    'most_frequent': str(value_counts.index[0]) if len(value_counts) > 0 else None,
                    'most_frequent_count': int(value_counts.iloc[0]) if len(value_counts) > 0 else 0,
                    'least_frequent': str(value_counts.index[-1]) if len(value_counts) > 0 else None,
                    'least_frequent_count': int(value_counts.iloc[-1]) if len(value_counts) > 0 else 0,
                    'top_5_values': value_counts.head(5).to_dict(),
                    'cardinality_ratio': float(df[col].nunique() / len(df)) if len(df) > 0 else 0
                }
            except Exception as e:
                logger.warning(f"Error analyzing categorical distribution for {col}: {str(e)}")
    
    return categorical_analysis

def validate_business_rules(df):
    """Validate business-specific rules based on notebook's domain knowledge"""
    business_validation = {
        'rules_passed': [],
        'rules_failed': [],
        'business_metrics': {}
    }
    
    try:
        # Rule 1: Orders should have positive quantities and prices
        if 'OrderUnits' in df.columns and 'Price' in df.columns:
            valid_orders = ((df['OrderUnits'] > 0) & (df['Price'] > 0)).sum()
            total_orders = len(df)
            business_validation['business_metrics']['valid_order_percentage'] = (valid_orders / total_orders * 100) if total_orders > 0 else 0
            
            if business_validation['business_metrics']['valid_order_percentage'] >= 95:
                business_validation['rules_passed'].append("Order validity check (>95% valid orders)")
            else:
                business_validation['rules_failed'].append(f"Order validity check failed ({business_validation['business_metrics']['valid_order_percentage']:.1f}% valid)")
        
        # Rule 2: Customer-Facility relationships should be consistent
        if 'CustomerID' in df.columns and 'FacilityID' in df.columns:
            customer_facilities = df.groupby('CustomerID')['FacilityID'].nunique()
            avg_facilities_per_customer = customer_facilities.mean()
            business_validation['business_metrics']['avg_facilities_per_customer'] = float(avg_facilities_per_customer)
            
            if avg_facilities_per_customer > 0:
                business_validation['rules_passed'].append("Customer-Facility relationships exist")
            else:
                business_validation['rules_failed'].append("No Customer-Facility relationships found")
        
        # Rule 3: Product categories should be properly assigned
        if 'ProductID' in df.columns and 'CategoryName' in df.columns:
            products_with_categories = df[df['CategoryName'].notna()]['ProductID'].nunique()
            total_products = df['ProductID'].nunique()
            category_coverage = (products_with_categories / total_products * 100) if total_products > 0 else 0
            business_validation['business_metrics']['product_category_coverage'] = category_coverage
            
            if category_coverage >= 90:
                business_validation['rules_passed'].append("Product categorization check (>90% coverage)")
            else:
                business_validation['rules_failed'].append(f"Product categorization incomplete ({category_coverage:.1f}% coverage)")
        
        # Rule 4: Date consistency (orders should be within reasonable timeframe)
        if 'CreateDate' in df.columns:
            try:
                dates = pd.to_datetime(df['CreateDate'])
                date_span = (dates.max() - dates.min()).days
                business_validation['business_metrics']['date_span_days'] = date_span
                
                if 30 <= date_span <= 365*3:  # Between 1 month and 3 years
                    business_validation['rules_passed'].append("Date range is reasonable")
                else:
                    business_validation['rules_failed'].append(f"Date range unusual ({date_span} days)")
            except:
                business_validation['rules_failed'].append("Date format validation failed")
        
        # Rule 5: Vendor-Product relationships
        if 'VendorID' in df.columns and 'ProductID' in df.columns:
            vendor_products = df.groupby('VendorID')['ProductID'].nunique()
            avg_products_per_vendor = vendor_products.mean()
            business_validation['business_metrics']['avg_products_per_vendor'] = float(avg_products_per_vendor)
            
            if avg_products_per_vendor >= 1:
                business_validation['rules_passed'].append("Vendor-Product relationships exist")
            else:
                business_validation['rules_failed'].append("Insufficient Vendor-Product relationships")
                
    except Exception as e:
        logger.error(f"Error in business rules validation: {str(e)}")
        business_validation['rules_failed'].append(f"Business validation error: {str(e)}")
    
    return business_validation

def generate_comprehensive_report(df):
    """Generate comprehensive data quality report matching notebook's format"""
    report = {
        'report_timestamp': datetime.now().isoformat(),
        'dataset_overview': {},
        'data_quality_score': 0,
        'recommendations': []
    }
    
    try:
        # Dataset overview (matching notebook's initial analysis)
        report['dataset_overview'] = {
            'total_records': len(df),
            'total_columns': len(df.columns),
            'memory_usage_mb': df.memory_usage(deep=True).sum() / 1024 / 1024,
            'duplicate_records': df.duplicated().sum(),
            'duplicate_percentage': (df.duplicated().sum() / len(df) * 100) if len(df) > 0 else 0
        }
        
        # Calculate data quality score
        quality_factors = []
        
        # Factor 1: Completeness (no missing values in critical columns)
        critical_columns = ['CustomerID', 'FacilityID', 'ProductID', 'CreateDate']
        missing_critical = sum(df[col].isnull().sum() for col in critical_columns if col in df.columns)
        completeness_score = max(0, 100 - (missing_critical / len(df) * 100)) if len(df) > 0 else 0
        quality_factors.append(completeness_score)
        
        # Factor 2: Validity (proper data types and formats)
        validity_issues = 0
        if 'CreateDate' in df.columns:
            try:
                pd.to_datetime(df['CreateDate'])
            except:
                validity_issues += 1
        
        if 'OrderUnits' in df.columns:
            validity_issues += (df['OrderUnits'] < 0).sum()
        
        validity_score = max(0, 100 - (validity_issues / len(df) * 100)) if len(df) > 0 else 0
        quality_factors.append(validity_score)
        
        # Factor 3: Consistency (no duplicates, consistent relationships)
        consistency_score = max(0, 100 - report['dataset_overview']['duplicate_percentage'])
        quality_factors.append(consistency_score)
        
        # Overall quality score
        report['data_quality_score'] = sum(quality_factors) / len(quality_factors) if quality_factors else 0
        
        # Generate recommendations
        if report['data_quality_score'] < 70:
            report['recommendations'].append("Data quality is below acceptable threshold (70%). Immediate attention required.")
        
        if report['dataset_overview']['duplicate_percentage'] > 5:
            report['recommendations'].append("High duplicate record percentage detected. Consider data deduplication.")
        
        if missing_critical > 0:
            report['recommendations'].append("Missing values found in critical columns. Data cleaning recommended.")
        
        if validity_issues > 0:
            report['recommendations'].append("Data validity issues detected. Review data formats and business rules.")
        
        if len(report['recommendations']) == 0:
            report['recommendations'].append("Data quality is acceptable. Continue with regular monitoring.")
            
    except Exception as e:
        logger.error(f"Error generating comprehensive report: {str(e)}")
        report['error'] = str(e)
    
    return report

def validate_data_quality(df):
    """Validate data quality and return validation results matching notebook's analysis"""
    validation_results = {
        'is_valid': True,
        'issues': [],
        'warnings': [],
        'stats': {},
        'data_profile': {}
    }
    
    # Check for required columns based on notebook schema
    required_columns = ['CustomerID', 'FacilityID', 'OrderID', 'ProductID', 'ProductName', 
                       'CategoryName', 'VendorID', 'VendorName', 'CreateDate', 'OrderUnits', 'Price']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        validation_results['is_valid'] = False
        validation_results['issues'].append(f"Missing required columns: {missing_columns}")
    
    # Data type validation
    expected_dtypes = {
        'CustomerID': ['int64', 'int32', 'object'],
        'FacilityID': ['int64', 'int32', 'object'], 
        'OrderID': ['int64', 'int32', 'object'],
        'ProductID': ['int64', 'int32', 'object'],
        'VendorID': ['int64', 'int32', 'object'],
        'OrderUnits': ['float64', 'int64', 'int32'],
        'Price': ['float64', 'int64', 'int32']
    }
    
    for col, valid_types in expected_dtypes.items():
        if col in df.columns and str(df[col].dtype) not in valid_types:
            validation_results['warnings'].append(f"Column {col} has unexpected data type: {df[col].dtype}")
    
    # Check for null values in critical columns (matching notebook's missing value check)
    missing_values = df.isnull().sum()
    critical_columns = ['CustomerID', 'FacilityID', 'ProductID', 'CreateDate', 'OrderUnits']
    
    for col in critical_columns:
        if col in df.columns:
            null_count = missing_values[col]
            if null_count > 0:
                validation_results['warnings'].append(f"Column {col} has {null_count} null values ({null_count/len(df)*100:.2f}%)")
                if null_count > len(df) * 0.1:  # More than 10% missing
                    validation_results['is_valid'] = False
                    validation_results['issues'].append(f"Column {col} has excessive null values: {null_count} ({null_count/len(df)*100:.2f}%)")
    
    # Date format validation and conversion (matching notebook's date handling)
    if 'CreateDate' in df.columns:
        try:
            # Try to convert dates - notebook uses pd.to_datetime
            date_series = pd.to_datetime(df['CreateDate'])
            
            # Check for invalid dates (NaT values after conversion)
            invalid_dates = date_series.isnull().sum()
            if invalid_dates > 0:
                validation_results['warnings'].append(f"Found {invalid_dates} invalid dates in CreateDate")
                
            # Date range validation (should be reasonable business dates)
            min_date = date_series.min()
            max_date = date_series.max()
            
            # Check if dates are in reasonable range (not too far in past/future)
            from datetime import datetime, timedelta
            current_date = datetime.now()
            if min_date < current_date - timedelta(days=365*5):  # More than 5 years ago
                validation_results['warnings'].append(f"Dates extend unusually far into past: {min_date}")
            if max_date > current_date + timedelta(days=365*2):  # More than 2 years in future
                validation_results['warnings'].append(f"Dates extend unusually far into future: {max_date}")
                
        except Exception as e:
            validation_results['is_valid'] = False
            validation_results['issues'].append(f"Invalid date format in CreateDate: {str(e)}")
    
    # Check for negative quantities (OrderUnits should be positive)
    if 'OrderUnits' in df.columns:
        negative_qty = (df['OrderUnits'] < 0).sum()
        zero_qty = (df['OrderUnits'] == 0).sum()
        if negative_qty > 0:
            validation_results['warnings'].append(f"Found {negative_qty} records with negative OrderUnits")
        if zero_qty > 0:
            validation_results['warnings'].append(f"Found {zero_qty} records with zero OrderUnits")
    
    # Check for negative prices
    if 'Price' in df.columns:
        negative_price = (df['Price'] < 0).sum()
        zero_price = (df['Price'] == 0).sum()
        if negative_price > 0:
            validation_results['warnings'].append(f"Found {negative_price} records with negative Price")
        if zero_price > 0:
            validation_results['warnings'].append(f"Found {zero_price} records with zero Price")
    
    # Statistical validation matching notebook's basic statistics
    validation_results['stats'] = {
        'dataset_shape': df.shape,
        'total_records': len(df),
        'memory_usage_mb': df.memory_usage(deep=True).sum() / 1024 / 1024
    }
    
    # Date range statistics (matching notebook output)
    if 'CreateDate' in df.columns:
        try:
            date_series = pd.to_datetime(df['CreateDate'])
            validation_results['stats']['date_range'] = {
                'start': str(date_series.min()),
                'end': str(date_series.max()),
                'span_days': (date_series.max() - date_series.min()).days
            }
        except:
            validation_results['stats']['date_range'] = {
                'start': None,
                'end': None,
                'span_days': None
            }
    
    # Unique counts (matching notebook's nunique() calls)
    unique_counts = {}
    count_columns = ['CustomerID', 'FacilityID', 'ProductID', 'OrderID', 'VendorID']
    for col in count_columns:
        if col in df.columns:
            unique_counts[f'unique_{col.lower()}'] = df[col].nunique()
    
    validation_results['stats'].update(unique_counts)
    
    # Data profiling metrics
    validation_results['data_profile'] = {
        'missing_values_summary': missing_values[missing_values > 0].to_dict(),
        'duplicate_records': df.duplicated().sum(),
        'columns_info': {
            'total_columns': len(df.columns),
            'numeric_columns': len(df.select_dtypes(include=['number']).columns),
            'text_columns': len(df.select_dtypes(include=['object']).columns),
            'datetime_columns': len(df.select_dtypes(include=['datetime']).columns)
        }
    }
    
    # Business logic validation
    if 'CustomerID' in df.columns and 'FacilityID' in df.columns:
        # Check customer-facility relationships
        customer_facility_pairs = df[['CustomerID', 'FacilityID']].drop_duplicates()
        validation_results['data_profile']['customer_facility_relationships'] = len(customer_facility_pairs)
    
    if 'ProductID' in df.columns and 'ProductName' in df.columns:
        # Check product ID to name consistency
        product_mapping = df[['ProductID', 'ProductName']].drop_duplicates()
        inconsistent_products = product_mapping.groupby('ProductID')['ProductName'].nunique()
        inconsistent_count = (inconsistent_products > 1).sum()
        if inconsistent_count > 0:
            validation_results['warnings'].append(f"Found {inconsistent_count} ProductIDs with multiple ProductNames")
    
    # Summary validation status
    if len(validation_results['issues']) == 0 and len(validation_results['warnings']) <= 5:
        validation_results['validation_summary'] = "PASSED"
    elif len(validation_results['issues']) == 0:
        validation_results['validation_summary'] = "PASSED_WITH_WARNINGS"
    else:
        validation_results['validation_summary'] = "FAILED"
        validation_results['is_valid'] = False
    
    return validation_results

def lambda_handler(event, context):
    """Lambda handler for data validation"""
    try:
        logger.info("Starting data validation process")
        
        # Parse S3 event
        for record in event['Records']:
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            logger.info(f"Processing file: s3://{bucket}/{key}")
            
            # Read the processed data
            response = s3_client.get_object(Bucket=bucket, Key=key)
            df = pd.read_csv(response['Body'])
            
            # Validate data quality
            validation_results = validate_data_quality(df)
            
            # Generate comprehensive data profiling
            logger.info("Generating comprehensive data profiling...")
            
            # Add distribution analysis
            validation_results['distribution_analysis'] = generate_data_distribution_analysis(df)
            
            # Add categorical analysis
            validation_results['categorical_analysis'] = analyze_categorical_distributions(df)
            
            # Add business rules validation
            validation_results['business_validation'] = validate_business_rules(df)
            
            # Generate comprehensive report
            validation_results['comprehensive_report'] = generate_comprehensive_report(df)
            
            # Save validation results
            validation_key = key.replace('processed/', 'validation/').replace('.csv', '_validation.json')
            
            s3_client.put_object(
                Bucket=processed_bucket,
                Key=validation_key,
                Body=json.dumps(validation_results, indent=2, default=str),
                ContentType='application/json'
            )
            
            logger.info(f"Validation results saved to: s3://{processed_bucket}/{validation_key}")
            
            # Save summary report separately for easy access
            summary_key = key.replace('processed/', 'validation/').replace('.csv', '_summary.json')
            summary_report = {
                'validation_summary': validation_results.get('validation_summary', 'UNKNOWN'),
                'data_quality_score': validation_results['comprehensive_report'].get('data_quality_score', 0),
                'total_records': validation_results['stats'].get('total_records', 0),
                'issues_count': len(validation_results.get('issues', [])),
                'warnings_count': len(validation_results.get('warnings', [])),
                'business_rules_passed': len(validation_results['business_validation'].get('rules_passed', [])),
                'business_rules_failed': len(validation_results['business_validation'].get('rules_failed', [])),
                'recommendations': validation_results['comprehensive_report'].get('recommendations', [])
            }
            
            s3_client.put_object(
                Bucket=processed_bucket,
                Key=summary_key,
                Body=json.dumps(summary_report, indent=2),
                ContentType='application/json'
            )
            
            logger.info(f"Summary report saved to: s3://{processed_bucket}/{summary_key}")
            
            # If validation fails, create an alert
            if not validation_results['is_valid']:
                logger.error(f"Data validation failed for {key}: {validation_results['issues']}")
                # Here you could send SNS notification or create CloudWatch alarm
            
            # Log summary statistics
            logger.info(f"Validation completed - Quality Score: {validation_results['comprehensive_report'].get('data_quality_score', 0):.1f}%, "
                       f"Issues: {len(validation_results.get('issues', []))}, "
                       f"Warnings: {len(validation_results.get('warnings', []))}")
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Data validation completed successfully',
                'validation_results': validation_results
            })
        }
        
    except Exception as e:
        logger.error(f"Error in data validation: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
