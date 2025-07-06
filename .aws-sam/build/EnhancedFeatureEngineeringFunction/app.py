import json
import boto3
import csv
import os
import logging
import urllib.parse
from datetime import datetime
import numpy as np
import pandas as pd

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

s3_client = boto3.client('s3')
processed_bucket = os.environ.get('PROCESSED_BUCKET')

def extract_temporal_features(df):
    """Extract time-based features from the CreateDate"""
    logger.info("Extracting temporal features...")
    
    # Convert date strings to datetime objects if needed
    if df['CreateDate'].dtype == 'object':
        df['CreateDate'] = pd.to_datetime(df['CreateDate'])
    
    # Basic date components
    df['OrderYear'] = df['CreateDate'].dt.year
    df['OrderMonth'] = df['CreateDate'].dt.month
    df['OrderDay'] = df['CreateDate'].dt.day
    df['OrderDayOfWeek'] = df['CreateDate'].dt.dayofweek  # Monday=0, Sunday=6
    df['OrderHour'] = df['CreateDate'].dt.hour
    
    # Cyclical encoding of time features
    df['DayOfWeek_sin'] = np.sin(df['OrderDayOfWeek'] * (2 * np.pi / 7))
    df['DayOfWeek_cos'] = np.cos(df['OrderDayOfWeek'] * (2 * np.pi / 7))
    
    df['DayOfMonth_sin'] = np.sin((df['OrderDay'] - 1) * (2 * np.pi / 31))
    df['DayOfMonth_cos'] = np.cos((df['OrderDay'] - 1) * (2 * np.pi / 31))
    
    df['MonthOfYear_sin'] = np.sin((df['OrderMonth'] - 1) * (2 * np.pi / 12))
    df['MonthOfYear_cos'] = np.cos((df['OrderMonth'] - 1) * (2 * np.pi / 12))
    
    # Quarter
    df['OrderQuarter'] = df['OrderMonth'].apply(lambda x: (x-1)//3 + 1)
    
    # Is weekend
    df['IsWeekend'] = df['OrderDayOfWeek'].apply(lambda x: 1 if x >= 5 else 0)
    
    # US holidays (simplified for 2025)
    holidays_2025 = {
        '2025-01-01': 'New Year\'s Day',
        '2025-01-20': 'Martin Luther King Jr. Day',
        '2025-02-17': 'Presidents\' Day',
        '2025-05-26': 'Memorial Day',
        '2025-06-19': 'Juneteenth',
        '2025-07-04': 'Independence Day',
        '2025-09-01': 'Labor Day',
        '2025-10-13': 'Columbus Day',
        '2025-11-11': 'Veterans Day',
        '2025-11-27': 'Thanksgiving Day',
        '2025-12-25': 'Christmas Day'
    }
    
    df['Date'] = df['CreateDate'].dt.strftime('%Y-%m-%d')
    df['IsHoliday'] = df['Date'].apply(lambda x: 1 if x in holidays_2025 else 0)
    df['HolidayName'] = df['Date'].apply(lambda x: holidays_2025.get(x, ''))
    
    return df

def calculate_product_demand_patterns(df):
    """Calculate product-specific demand patterns for individual products"""
    logger.info("Calculating product demand patterns...")
    
    # Group by customer, facility, product, and date to get daily quantities
    product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information back
    product_info = df[['ProductID', 'ProductDescription', 'ProductCategory']].drop_duplicates()
    product_daily = product_daily.merge(product_info, on='ProductID', how='left')
    
    # Calculate product-specific features
    product_groups = product_daily.groupby(['CustomerID', 'FacilityID', 'ProductID'])
    
    product_features = []
    for (customer_id, facility_id, product_id), group in product_groups:
        # Sort by date
        group_sorted = group.sort_values('Date')
        
        # Calculate features
        total_orders = len(group_sorted)
        avg_quantity = group_sorted['Quantity'].mean()
        std_quantity = group_sorted['Quantity'].std()
        max_quantity = group_sorted['Quantity'].max()
        min_quantity = group_sorted['Quantity'].min()
        
        # Calculate order frequency (days between orders)
        if total_orders > 1:
            date_range = (pd.to_datetime(group_sorted['Date'].max()) - pd.to_datetime(group_sorted['Date'].min())).days
            avg_days_between_orders = date_range / (total_orders - 1) if total_orders > 1 else np.nan
        else:
            avg_days_between_orders = np.nan
        
        # Get product info
        product_name = group_sorted['ProductDescription'].iloc[0]
        category_name = group_sorted['ProductCategory'].iloc[0]
        
        product_features.append({
            'CustomerID': customer_id,
            'FacilityID': facility_id,
            'ProductID': product_id,
            'ProductName': product_name,
            'CategoryName': category_name,
            'TotalOrders': total_orders,
            'AvgQuantity': avg_quantity,
            'StdQuantity': std_quantity if not pd.isna(std_quantity) else 0,
            'MaxQuantity': max_quantity,
            'MinQuantity': min_quantity,
            'AvgDaysBetweenOrders': avg_days_between_orders
        })
    
    return pd.DataFrame(product_features)

def prepare_product_forecast_data(df):
    """Prepare data for product-level forecasting"""
    logger.info("Preparing product-level forecast data...")
    
    # Group by customer, facility, product, and date
    product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information
    product_info = df[['ProductID', 'ProductDescription', 'ProductCategory']].drop_duplicates()
    product_daily = product_daily.merge(product_info, on='ProductID', how='left')
    
    # Create item_id that includes ProductID for better identification
    forecast_df = pd.DataFrame({
        'item_id': (product_daily['CustomerID'].astype(str) + '_' + 
                   product_daily['FacilityID'].astype(str) + '_' + 
                   product_daily['ProductID'].astype(str)),
        'timestamp': product_daily['Date'],
        'target_value': product_daily['Quantity'],
        'customer_id': product_daily['CustomerID'],
        'facility_id': product_daily['FacilityID'],
        'product_id': product_daily['ProductID'],
        'product_name': product_daily['ProductDescription'],
        'category_name': product_daily['ProductCategory']
    })
    
    return forecast_df

def prepare_customer_level_forecast_data(df):
    """Prepare data for customer-level forecasting (total order volume)"""
    logger.info("Preparing customer-level forecast data...")
    
    # Group by customer, facility, and date for total order count
    customer_daily = df.groupby(['CustomerID', 'FacilityID', 'Date']).size().reset_index(name='TotalItems')
    
    # Also calculate unique products ordered per day
    unique_products_daily = df.groupby(['CustomerID', 'FacilityID', 'Date'])['ProductID'].nunique().reset_index(name='UniqueProducts')
    
    # Merge the data
    customer_daily = customer_daily.merge(unique_products_daily, on=['CustomerID', 'FacilityID', 'Date'])
    
    # Create forecast format for total items
    forecast_df_items = pd.DataFrame({
        'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                   customer_daily['FacilityID'].astype(str) + '_TOTAL_ITEMS'),
        'timestamp': customer_daily['Date'],
        'target_value': customer_daily['TotalItems'],
        'customer_id': customer_daily['CustomerID'],
        'facility_id': customer_daily['FacilityID'],
        'metric_type': 'TOTAL_ITEMS'
    })
    
    # Create forecast format for unique products
    forecast_df_products = pd.DataFrame({
        'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                   customer_daily['FacilityID'].astype(str) + '_UNIQUE_PRODUCTS'),
        'timestamp': customer_daily['Date'],
        'target_value': customer_daily['UniqueProducts'],
        'customer_id': customer_daily['CustomerID'],
        'facility_id': customer_daily['FacilityID'],
        'metric_type': 'UNIQUE_PRODUCTS'
    })
    
    # Combine both datasets
    forecast_df = pd.concat([forecast_df_items, forecast_df_products], ignore_index=True)
    
    return forecast_df

def create_product_lookup_table(df):
    """Create a lookup table for product information"""
    logger.info("Creating product lookup table...")
    
    product_lookup = df[['ProductID', 'ProductDescription', 'ProductCategory']].drop_duplicates()
    
    # Add customer-product relationships
    customer_products = df.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg({
        'Quantity': 'nunique',  # Number of times ordered
        'CreateDate': ['min', 'max']  # First and last order dates
    }).reset_index()
    
    # Flatten column names
    customer_products.columns = ['CustomerID', 'FacilityID', 'ProductID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate']
    
    # Merge with product info
    customer_product_lookup = customer_products.merge(product_lookup, on='ProductID', how='left')
    
    return product_lookup, customer_product_lookup

def process_csv_data(file_path):
    """Process CSV data without pandas"""
    logger.info("Processing CSV data...")
    
    processed_data = []
    with open(file_path, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Basic date processing
            create_date = datetime.strptime(row['CreateDate'], '%m/%d/%y')
            row['OrderYear'] = create_date.year
            row['OrderMonth'] = create_date.month
            row['OrderDay'] = create_date.day
            row['OrderDayOfWeek'] = create_date.weekday()
            row['IsWeekend'] = 1 if create_date.weekday() >= 5 else 0
            row['Date'] = create_date.strftime('%Y-%m-%d')
            processed_data.append(row)
    
    return processed_data

def create_lookup_files(df):
    """Create product and customer-product lookup files"""
    # Product Lookup
    product_lookup = df[['ProductID', 'ProductDescription', 'ProductCategory']].drop_duplicates()
    product_lookup.rename(columns={'ProductDescription': 'ProductName', 'ProductCategory': 'CategoryName'}, inplace=True)
    product_lookup['vendorName'] = 'Vendor' + product_lookup['ProductID'].astype(str).str.replace('PROD', '')

    # Customer-Product Lookup
    customer_product_lookup = df.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg(
        OrderCount=('Quantity', 'count'),
        FirstOrderDate=('CreateDate', 'min'),
        LastOrderDate=('CreateDate', 'max')
    ).reset_index()

    # Merge with product details
    customer_product_lookup = pd.merge(customer_product_lookup, product_lookup, on='ProductID')
    
    return product_lookup, customer_product_lookup

def lambda_handler(event, context):
    """Lambda function handler to process S3 data and create lookups"""
    try:
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
        
        logger.info(f"Processing file {key} from bucket {bucket}")
        
        download_path = f'/tmp/{os.path.basename(key)}'
        s3_client.download_file(bucket, key, download_path)
        
        # Process data with pandas
        df = pd.read_csv(download_path)
        logger.info(f"Loaded {len(df)} rows of data")

        # Normalize column names: strip spaces, make consistent case
        df.columns = [col.strip().replace(' ', '').replace('_', '').title() for col in df.columns]
        # Try to match expected columns
        
        col_map = {
            'Customerid': 'CustomerID',
            'Facilityid': 'FacilityID',
            'Productid': 'ProductID',
            'Productdescription': 'ProductDescription',
            'Productcategory': 'ProductCategory',
            'Createdate': 'CreateDate',
            'Quantity': 'Quantity'
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
        df['CreateDate'] = pd.to_datetime(df['CreateDate'], format='%m/%d/%y')

        # Feature engineering
        df = extract_temporal_features(df)
        
        # Calculate product demand patterns
        product_features = calculate_product_demand_patterns(df)
        
        # Create lookup tables
        product_lookup, customer_product_lookup = create_product_lookup_table(df)
        
        # Prepare forecast data at different levels
        product_forecast_df = prepare_product_forecast_data(df)
        customer_forecast_df = prepare_customer_level_forecast_data(df)
        
        # Save all the processed data
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        
        
        # Save product features
        product_features_file = f'/tmp/product_features_{timestamp}.csv'
        product_features.to_csv(product_features_file, index=False)
        product_features_key = f'processed/{timestamp}/product_features.csv'
        s3_client.upload_file(product_features_file, processed_bucket, product_features_key)
        
        # Save product lookup
        product_lookup_file = f'/tmp/product_lookup_{timestamp}.csv'
        product_lookup.to_csv(product_lookup_file, index=False)
        product_lookup_key = f'lookup/{timestamp}/product_lookup.csv'
        s3_client.upload_file(product_lookup_file, processed_bucket, product_lookup_key)
        
        # Save customer-product lookup
        customer_product_lookup_file = f'/tmp/customer_product_lookup_{timestamp}.csv'
        customer_product_lookup.to_csv(customer_product_lookup_file, index=False)
        customer_product_lookup_key = f'lookup/{timestamp}/customer_product_lookup.csv'
        s3_client.upload_file(customer_product_lookup_file, processed_bucket, customer_product_lookup_key)
        
        # Save product-level forecast data
        product_forecast_file = f'/tmp/product_forecast_data_{timestamp}.csv'
        product_forecast_df.to_csv(product_forecast_file, index=False)
        product_forecast_key = f'forecast_format/{timestamp}/product_forecast_data.csv'
        s3_client.upload_file(product_forecast_file, processed_bucket, product_forecast_key)
        
        # Save customer-level forecast data
        customer_forecast_file = f'/tmp/customer_forecast_data_{timestamp}.csv'
        customer_forecast_df.to_csv(customer_forecast_file, index=False)
        customer_forecast_key = f'forecast_format/{timestamp}/customer_forecast_data.csv'
        s3_client.upload_file(customer_forecast_file, processed_bucket, customer_forecast_key)
        
        logger.info(f"Successfully processed and uploaded all data files")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully processed {len(df)} records',
                'product_features_location': f's3://{processed_bucket}/{product_features_key}',
                'product_lookup_location': f's3://{processed_bucket}/{product_lookup_key}',
                'customer_product_lookup_location': f's3://{processed_bucket}/{customer_product_lookup_key}',
                'product_forecast_location': f's3://{processed_bucket}/{product_forecast_key}',
                'customer_forecast_location': f's3://{processed_bucket}/{customer_forecast_key}',
                'total_unique_products': len(product_lookup),
                'total_customer_product_combinations': len(customer_product_lookup)
            })
        }
        ##here

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error processing file: {str(e)}'
            })
        }
