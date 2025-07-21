# Design Document

## Overview

This design outlines the systematic update of existing Lambda functions to align with the working implementation in hybrent.ipynb. The notebook demonstrates a complete end-to-end product-level forecasting solution using Amazon SageMaker DeepAR, Amazon Bedrock for recommendations, and comprehensive feature engineering. The design ensures production Lambda functions replicate this proven functionality.

## Architecture

The system maintains the existing serverless architecture with enhanced functionality:

```
Raw Data (S3) → Enhanced Feature Engineering → Data Validation → SageMaker Training/Inference → Enhanced Predictions → API Endpoints
                      ↓                           ↓                        ↓                         ↓
                Product Lookups              Validation Results        Model Artifacts         Bedrock Insights
                (S3 + DynamoDB)                   (S3)                    (S3)              (Real-time API)
```

### Key Components

1. **Enhanced Feature Engineering Lambda**: Implements notebook's temporal feature extraction, product demand patterns, and lookup table creation
2. **Data Validation Lambda**: Applies notebook's data quality checks and validation rules
3. **Enhanced Predictions Lambda**: Uses notebook's SageMaker DeepAR integration and Bedrock recommendation logic
4. **API Gateway Endpoints**: Return predictions in notebook's JSON format with consistent data structures

## Components and Interfaces

### Enhanced Feature Engineering Function

**Purpose**: Process raw CSV data using the exact feature engineering logic from the notebook

**Key Updates**:
- Implement `extract_temporal_features()` function from notebook with cyclical encoding
- Add `calculate_product_demand_patterns()` for individual product analysis
- Create `prepare_product_forecast_data()` and `prepare_customer_level_forecast_data()` functions
- Generate product lookup tables matching notebook's schema
- Add dynamic holiday detection for current year (improving upon notebook's hardcoded 2025 holidays)
- Include weekend flags and seasonal patterns as shown in notebook

**Input**: S3 CSV files (triggered by S3 events)
**Output**: 
- Processed feature files in S3
- Product lookup tables in S3 and DynamoDB
- Customer-product relationship data

**Interface Changes**:
```python
def extract_temporal_features(df):
    # Cyclical encoding for time features
    # Dynamic holiday detection for US holidays (current year + future years)
    # Weekend flags and quarter calculations
    
def get_us_holidays(year):
    # Dynamic holiday calculation for any year
    # Replaces notebook's hardcoded 2025 holidays
    # Supports federal holidays with proper date calculations

def calculate_product_demand_patterns(df):
    # Product-specific demand analysis
    # Order frequency calculations
    # Statistical features per product

def prepare_product_forecast_data(df):
    # Format data for SageMaker DeepAR
    # Create item_id with customer_facility_product format
```

### Enhanced Predictions Function

**Purpose**: Generate predictions using notebook's SageMaker DeepAR approach and Bedrock integration

**Key Updates**:
- Implement `query_sagemaker_for_predictions()` matching notebook's endpoint invocation
- Add `call_bedrock_for_product_recommendations()` with notebook's prompt strategy
- Update response format to match notebook's JSON structure
- Implement fallback recommendation logic from notebook

**Input**: Customer ID, Facility ID via API Gateway
**Output**: Product predictions with Bedrock-generated insights in notebook format

**Interface Changes**:
```python
def query_sagemaker_for_predictions(customer_id, facility_id, product_lookup_df, customer_product_lookup_df):
    # Use notebook's SageMaker endpoint invocation pattern
    # Format input data exactly as notebook demonstrates
    # Parse responses using notebook's logic

def call_bedrock_for_product_recommendations(product_predictions, customer_id, facility_id):
    # Use notebook's Bedrock prompt template
    # Apply same model parameters and temperature settings
    # Return structured recommendations as in notebook
```

### Data Validation Function

**Purpose**: Apply notebook's data quality validation rules

**Key Updates**:
- Implement validation checks matching notebook's data exploration
- Add statistical validation based on notebook's data analysis
- Generate validation reports in notebook's format
- Include data profiling metrics shown in notebook

**Interface Changes**:
```python
def validate_data_quality(df):
    # Apply notebook's validation rules
    # Check for required columns and data types
    # Validate date ranges and statistical distributions
    # Generate comprehensive validation reports
```

### API Functions Updates

**Purpose**: Return data in notebook's JSON format with consistent structure

**Key Updates**:
- Update response schemas to match notebook output format
- Add product-level prediction endpoints as demonstrated in notebook
- Include recommendation data structures from notebook
- Maintain backward compatibility with existing API contracts

## Data Models

### Product Lookup Schema (from notebook)
```python
{
    'ProductID': str,
    'ProductName': str,
    'CategoryName': str,
    'vendorName': str,
    'CustomerID': str,
    'FacilityID': str,
    'OrderCount': int,
    'FirstOrderDate': datetime,
    'LastOrderDate': datetime
}
```

### Prediction Response Schema (from notebook)
```python
{
    'id': str,
    'timestamp': datetime,
    'customerId': str,
    'facilityId': str,
    'productPredictions': [
        {
            'product_id': str,
            'product_name': str,
            'category_name': str,
            'vendor_name': str,
            'predictions': {
                'YYYY-MM-DD': {
                    'p10': float,
                    'p50': float,
                    'p90': float,
                    'mean': float
                }
            },
            'order_history': {
                'order_count': int,
                'first_order': str,
                'last_order': str
            }
        }
    ],
    'recommendations': {
        'recommended_products': [...],
        'ordering_schedule': [...],
        'insights': {...}
    }
}
```

### Feature Engineering Output Schema (from notebook)
```python
{
    'temporal_features': {
        'OrderYear': int,
        'OrderMonth': int,
        'OrderDay': int,
        'OrderDayOfWeek': int,
        'DayOfWeek_sin': float,
        'DayOfWeek_cos': float,
        'MonthOfYear_sin': float,
        'MonthOfYear_cos': float,
        'IsWeekend': int,
        'IsHoliday': int,
        'HolidayName': str
    },
    'product_features': {
        'TotalOrders': int,
        'AvgQuantity': float,
        'StdQuantity': float,
        'AvgDaysBetweenOrders': float
    }
}
```

## Error Handling

### Notebook-Based Error Patterns
- Implement try-catch blocks matching notebook's error handling
- Use same logging patterns and error messages as notebook
- Apply notebook's fallback strategies for missing data
- Generate mock data using notebook's mock generation logic

### Validation Error Handling
- Apply notebook's data quality thresholds
- Use same warning and error categorization as notebook
- Implement notebook's data cleaning strategies
- Generate validation reports in notebook's format

## Testing Strategy

### Unit Testing
- Test each function against notebook's expected outputs
- Validate feature engineering produces identical results to notebook
- Verify SageMaker integration matches notebook's approach
- Confirm Bedrock responses follow notebook's format

### Integration Testing
- End-to-end testing using notebook's sample data
- Validate API responses match notebook's JSON structure
- Test error scenarios using notebook's edge cases
- Verify performance matches notebook's processing times

### Data Validation Testing
- Use notebook's validation test cases
- Verify statistical calculations match notebook results
- Test data quality thresholds from notebook
- Validate lookup table generation against notebook output

## Implementation Notes

### Dependencies
- Ensure Lambda layers include all packages used in notebook (pandas, numpy, boto3, etc.)
- Match package versions to notebook's environment where possible
- Include any custom utilities or helper functions from notebook

### Configuration
- Use same SageMaker endpoint configuration as notebook
- Apply identical Bedrock model parameters from notebook
- Maintain consistent S3 bucket structure as demonstrated in notebook
- Use same DynamoDB table schemas implied by notebook

### Performance Considerations
- Implement notebook's data processing optimizations
- Use same batch processing strategies as notebook
- Apply notebook's memory management techniques
- Maintain notebook's timeout and retry logic