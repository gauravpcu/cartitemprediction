import json
import csv
import os
import logging
import urllib.parse
from datetime import datetime, date

# Import dependencies with error handling
try:
    import boto3
    import pandas as pd
    import numpy as np
except ImportError as e:
    logging.error(f"Failed to import required dependencies: {e}")
    raise

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
processed_bucket = os.environ.get('PROCESSED_BUCKET')
product_lookup_table = os.environ.get('PRODUCT_LOOKUP_TABLE', 'product-lookup')

def get_us_holidays(year):
    """Get US federal holidays for a given year with proper date calculations"""
    holidays = {}
    
    # Fixed date holidays
    holidays[f'{year}-01-01'] = "New Year's Day"
    holidays[f'{year}-06-19'] = "Juneteenth"
    holidays[f'{year}-07-04'] = "Independence Day"
    holidays[f'{year}-11-11'] = "Veterans Day"
    holidays[f'{year}-12-25'] = "Christmas Day"
    
    # Calculate variable date holidays
    # Martin Luther King Jr. Day - 3rd Monday in January
    jan_1 = date(year, 1, 1)
    days_to_first_monday = (7 - jan_1.weekday()) % 7
    first_monday_jan = jan_1 + pd.Timedelta(days=days_to_first_monday)
    mlk_day = first_monday_jan + pd.Timedelta(days=14)  # 3rd Monday
    holidays[mlk_day.strftime('%Y-%m-%d')] = "Martin Luther King Jr. Day"
    
    # Presidents' Day - 3rd Monday in February
    feb_1 = date(year, 2, 1)
    days_to_first_monday = (7 - feb_1.weekday()) % 7
    first_monday_feb = feb_1 + pd.Timedelta(days=days_to_first_monday)
    presidents_day = first_monday_feb + pd.Timedelta(days=14)  # 3rd Monday
    holidays[presidents_day.strftime('%Y-%m-%d')] = "Presidents' Day"
    
    # Memorial Day - Last Monday in May
    may_31 = date(year, 5, 31)
    weekday = may_31.weekday()  # 0=Monday, 1=Tuesday, ..., 6=Sunday
    if weekday == 0:  # Already Monday
        days_back = 0
    else:
        days_back = weekday
    memorial_day = may_31 - pd.Timedelta(days=days_back)
    holidays[memorial_day.strftime('%Y-%m-%d')] = "Memorial Day"
    
    # Labor Day - 1st Monday in September
    sep_1 = date(year, 9, 1)
    days_to_first_monday = (7 - sep_1.weekday()) % 7
    labor_day = sep_1 + pd.Timedelta(days=days_to_first_monday)
    holidays[labor_day.strftime('%Y-%m-%d')] = "Labor Day"
    
    # Columbus Day - 2nd Monday in October
    oct_1 = date(year, 10, 1)
    days_to_first_monday = (7 - oct_1.weekday()) % 7
    first_monday_oct = oct_1 + pd.Timedelta(days=days_to_first_monday)
    columbus_day = first_monday_oct + pd.Timedelta(days=7)  # 2nd Monday
    holidays[columbus_day.strftime('%Y-%m-%d')] = "Columbus Day"
    
    # Thanksgiving Day - 4th Thursday in November
    nov_1 = date(year, 11, 1)
    days_to_first_thursday = (3 - nov_1.weekday()) % 7
    first_thursday_nov = nov_1 + pd.Timedelta(days=days_to_first_thursday)
    thanksgiving_day = first_thursday_nov + pd.Timedelta(days=21)  # 4th Thursday
    holidays[thanksgiving_day.strftime('%Y-%m-%d')] = "Thanksgiving Day"
    
    return holidays

def extract_temporal_features(df):
    """Extract time-based features from the CreateDate"""
    logger.info("Extracting temporal features...")
    
    # Convert date strings to datetime objects with flexible parsing
    if df['CreateDate'].dtype == 'object':
        # Try multiple date formats
        try:
            df['CreateDate'] = pd.to_datetime(df['CreateDate'], infer_datetime_format=True)
        except:
            # Fallback to common formats
            for fmt in ['%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y']:
                try:
                    df['CreateDate'] = pd.to_datetime(df['CreateDate'], format=fmt)
                    logger.info(f"Successfully parsed dates using format: {fmt}")
                    break
                except:
                    continue
            else:
                # If all formats fail, use pandas' flexible parser
                df['CreateDate'] = pd.to_datetime(df['CreateDate'], errors='coerce')
    
    # Basic date components
    df['OrderYear'] = df['CreateDate'].dt.year
    df['OrderMonth'] = df['CreateDate'].dt.month
    df['OrderDay'] = df['CreateDate'].dt.day
    df['OrderDayOfWeek'] = df['CreateDate'].dt.dayofweek  # Monday=0, Sunday=6
    df['OrderHour'] = df['CreateDate'].dt.hour
    
    # Cyclical encoding of time features - matching notebook implementation exactly
    df['DayOfWeek_sin'] = np.sin(df['OrderDayOfWeek'] * (2 * np.pi / 7))
    df['DayOfWeek_cos'] = np.cos(df['OrderDayOfWeek'] * (2 * np.pi / 7))
    
    df['DayOfMonth_sin'] = np.sin((df['OrderDay'] - 1) * (2 * np.pi / 31))
    df['DayOfMonth_cos'] = np.cos((df['OrderDay'] - 1) * (2 * np.pi / 31))
    
    df['MonthOfYear_sin'] = np.sin((df['OrderMonth'] - 1) * (2 * np.pi / 12))
    df['MonthOfYear_cos'] = np.cos((df['OrderMonth'] - 1) * (2 * np.pi / 12))
    
    # Quarter - matching notebook implementation exactly
    df['OrderQuarter'] = df['OrderMonth'].apply(lambda x: (x-1)//3 + 1)
    
    # Is weekend - matching notebook implementation exactly
    df['IsWeekend'] = df['OrderDayOfWeek'].apply(lambda x: 1 if x >= 5 else 0)
    
    # Get dynamic US holidays for the years present in the data
    years_in_data = df['OrderYear'].unique()
    all_holidays = {}
    for year in years_in_data:
        year_holidays = get_us_holidays(year)
        all_holidays.update(year_holidays)
    
    df['Date'] = df['CreateDate'].dt.strftime('%Y-%m-%d')
    df['IsHoliday'] = df['Date'].apply(lambda x: 1 if x in all_holidays else 0)
    df['HolidayName'] = df['Date'].apply(lambda x: all_holidays.get(x, ''))
    
    return df

def calculate_product_demand_patterns(df):
    """Calculate product-specific demand patterns for individual products"""
    logger.info("Calculating product demand patterns...")
    
    # Group by customer, facility, product, and date to get daily quantities
    # Use OrderUnits if available, otherwise count occurrences
    if 'OrderUnits' in df.columns:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date'])['OrderUnits'].sum().reset_index(name='Quantity')
    else:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information back - handle different column names
    product_cols = ['ProductID']
    if 'ProductDescription' in df.columns:
        product_cols.append('ProductDescription')
    elif 'ProductName' in df.columns:
        product_cols.append('ProductName')
    
    if 'ProductCategory' in df.columns:
        product_cols.append('ProductCategory')
    elif 'CategoryName' in df.columns:
        product_cols.append('CategoryName')
    
    if 'VendorName' in df.columns:
        product_cols.append('VendorName')
    
    product_info = df[product_cols].drop_duplicates()
    product_daily = product_daily.merge(product_info, on='ProductID', how='left')
    
    # Calculate product-specific features
    product_groups = product_daily.groupby(['CustomerID', 'FacilityID', 'ProductID'])
    
    product_features = []
    for (customer_id, facility_id, product_id), group in product_groups:
        # Sort by date
        group_sorted = group.sort_values('Date')
        
        # Calculate basic statistics
        total_orders = len(group_sorted)
        avg_quantity = group_sorted['Quantity'].mean()
        std_quantity = group_sorted['Quantity'].std()
        max_quantity = group_sorted['Quantity'].max()
        min_quantity = group_sorted['Quantity'].min()
        median_quantity = group_sorted['Quantity'].median()
        
        # Calculate order frequency (days between orders)
        if total_orders > 1:
            date_range = (pd.to_datetime(group_sorted['Date'].max()) - pd.to_datetime(group_sorted['Date'].min())).days
            avg_days_between_orders = date_range / (total_orders - 1) if total_orders > 1 else np.nan
        else:
            avg_days_between_orders = np.nan
        
        # Calculate coefficient of variation (volatility measure)
        cv = std_quantity / avg_quantity if avg_quantity > 0 else 0
        
        # Calculate trend (simple linear trend over time)
        if total_orders > 2:
            dates_numeric = pd.to_datetime(group_sorted['Date']).astype(int) / 10**9  # Convert to seconds
            trend_slope = np.polyfit(dates_numeric, group_sorted['Quantity'], 1)[0]
        else:
            trend_slope = 0
        
        # Get product info with fallback names
        product_name = ''
        if 'ProductDescription' in group_sorted.columns:
            product_name = group_sorted['ProductDescription'].iloc[0]
        elif 'ProductName' in group_sorted.columns:
            product_name = group_sorted['ProductName'].iloc[0]
        
        category_name = ''
        if 'ProductCategory' in group_sorted.columns:
            category_name = group_sorted['ProductCategory'].iloc[0]
        elif 'CategoryName' in group_sorted.columns:
            category_name = group_sorted['CategoryName'].iloc[0]
        
        vendor_name = ''
        if 'VendorName' in group_sorted.columns:
            vendor_name = group_sorted['VendorName'].iloc[0]
        
        # Get first and last order dates
        first_order_date = group_sorted['Date'].min()
        last_order_date = group_sorted['Date'].max()
        
        product_features.append({
            'CustomerID': customer_id,
            'FacilityID': facility_id,
            'ProductID': product_id,
            'ProductName': product_name,
            'CategoryName': category_name,
            'VendorName': vendor_name,
            'TotalOrders': total_orders,
            'AvgQuantity': avg_quantity,
            'StdQuantity': std_quantity if not pd.isna(std_quantity) else 0,
            'MaxQuantity': max_quantity,
            'MinQuantity': min_quantity,
            'MedianQuantity': median_quantity,
            'CoefficientOfVariation': cv,
            'TrendSlope': trend_slope,
            'AvgDaysBetweenOrders': avg_days_between_orders,
            'FirstOrderDate': first_order_date,
            'LastOrderDate': last_order_date
        })
    
    return pd.DataFrame(product_features)

def prepare_product_forecast_data(df):
    """Prepare data for product-level forecasting in SageMaker DeepAR format"""
    logger.info("Preparing product-level forecast data...")
    
    # Group by customer, facility, product, and date to get daily quantities
    if 'OrderUnits' in df.columns:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date'])['OrderUnits'].sum().reset_index(name='Quantity')
    else:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information - handle different column names
    product_cols = ['ProductID']
    if 'ProductDescription' in df.columns:
        product_cols.append('ProductDescription')
    elif 'ProductName' in df.columns:
        product_cols.append('ProductName')
    
    if 'ProductCategory' in df.columns:
        product_cols.append('ProductCategory')
    elif 'CategoryName' in df.columns:
        product_cols.append('CategoryName')
    
    if 'VendorName' in df.columns:
        product_cols.append('VendorName')
    
    product_info = df[product_cols].drop_duplicates()
    product_daily = product_daily.merge(product_info, on='ProductID', how='left')
    
    # Create item_id that includes customer, facility, and product for unique identification
    forecast_df = pd.DataFrame({
        'item_id': (product_daily['CustomerID'].astype(str) + '_' + 
                   product_daily['FacilityID'].astype(str) + '_' + 
                   product_daily['ProductID'].astype(str)),
        'timestamp': pd.to_datetime(product_daily['Date']),
        'target_value': product_daily['Quantity'],
        'customer_id': product_daily['CustomerID'],
        'facility_id': product_daily['FacilityID'],
        'product_id': product_daily['ProductID']
    })
    
    # Add product metadata
    if 'ProductDescription' in product_daily.columns:
        forecast_df['product_name'] = product_daily['ProductDescription']
    elif 'ProductName' in product_daily.columns:
        forecast_df['product_name'] = product_daily['ProductName']
    else:
        forecast_df['product_name'] = 'Product ' + forecast_df['product_id'].astype(str)
    
    if 'ProductCategory' in product_daily.columns:
        forecast_df['category_name'] = product_daily['ProductCategory']
    elif 'CategoryName' in product_daily.columns:
        forecast_df['category_name'] = product_daily['CategoryName']
    else:
        forecast_df['category_name'] = 'General'
    
    if 'VendorName' in product_daily.columns:
        forecast_df['vendor_name'] = product_daily['VendorName']
    else:
        forecast_df['vendor_name'] = 'Vendor' + forecast_df['product_id'].astype(str).str.replace('PROD', '')
    
    # Add temporal features required for SageMaker DeepAR (matching notebook implementation)
    forecast_df['day_of_week'] = forecast_df['timestamp'].dt.dayofweek
    forecast_df['month'] = forecast_df['timestamp'].dt.month
    
    # Sort by item_id and timestamp for proper time series format
    forecast_df = forecast_df.sort_values(['item_id', 'timestamp']).reset_index(drop=True)
    
    return forecast_df

def prepare_customer_level_forecast_data(df):
    """Prepare data for customer-level forecasting (aggregated forecasts)"""
    logger.info("Preparing customer-level forecast data...")
    
    # Group by customer, facility, and date for total order count
    if 'OrderUnits' in df.columns:
        customer_daily = df.groupby(['CustomerID', 'FacilityID', 'Date'])['OrderUnits'].sum().reset_index(name='TotalUnits')
    else:
        customer_daily = df.groupby(['CustomerID', 'FacilityID', 'Date']).size().reset_index(name='TotalItems')
    
    # Also calculate unique products ordered per day
    unique_products_daily = df.groupby(['CustomerID', 'FacilityID', 'Date'])['ProductID'].nunique().reset_index(name='UniqueProducts')
    
    # Calculate total order value if Price column exists
    if 'Price' in df.columns:
        if 'OrderUnits' in df.columns:
            df['OrderValue'] = df['OrderUnits'] * df['Price']
        else:
            df['OrderValue'] = df['Price']
        order_value_daily = df.groupby(['CustomerID', 'FacilityID', 'Date'])['OrderValue'].sum().reset_index(name='TotalValue')
        customer_daily = customer_daily.merge(order_value_daily, on=['CustomerID', 'FacilityID', 'Date'])
    
    # Merge the data
    customer_daily = customer_daily.merge(unique_products_daily, on=['CustomerID', 'FacilityID', 'Date'])
    
    # Create forecast format for total items/units
    if 'TotalUnits' in customer_daily.columns:
        forecast_df_items = pd.DataFrame({
            'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                       customer_daily['FacilityID'].astype(str) + '_TOTAL_UNITS'),
            'timestamp': pd.to_datetime(customer_daily['Date']),
            'target_value': customer_daily['TotalUnits'],
            'customer_id': customer_daily['CustomerID'],
            'facility_id': customer_daily['FacilityID'],
            'metric_type': 'TOTAL_UNITS'
        })
    else:
        forecast_df_items = pd.DataFrame({
            'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                       customer_daily['FacilityID'].astype(str) + '_TOTAL_ITEMS'),
            'timestamp': pd.to_datetime(customer_daily['Date']),
            'target_value': customer_daily['TotalItems'],
            'customer_id': customer_daily['CustomerID'],
            'facility_id': customer_daily['FacilityID'],
            'metric_type': 'TOTAL_ITEMS'
        })
    
    # Create forecast format for unique products
    forecast_df_products = pd.DataFrame({
        'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                   customer_daily['FacilityID'].astype(str) + '_UNIQUE_PRODUCTS'),
        'timestamp': pd.to_datetime(customer_daily['Date']),
        'target_value': customer_daily['UniqueProducts'],
        'customer_id': customer_daily['CustomerID'],
        'facility_id': customer_daily['FacilityID'],
        'metric_type': 'UNIQUE_PRODUCTS'
    })
    
    # Create forecast format for total value if available
    forecast_dfs = [forecast_df_items, forecast_df_products]
    if 'TotalValue' in customer_daily.columns:
        forecast_df_value = pd.DataFrame({
            'item_id': (customer_daily['CustomerID'].astype(str) + '_' + 
                       customer_daily['FacilityID'].astype(str) + '_TOTAL_VALUE'),
            'timestamp': pd.to_datetime(customer_daily['Date']),
            'target_value': customer_daily['TotalValue'],
            'customer_id': customer_daily['CustomerID'],
            'facility_id': customer_daily['FacilityID'],
            'metric_type': 'TOTAL_VALUE'
        })
        forecast_dfs.append(forecast_df_value)
    
    # Combine all datasets
    forecast_df = pd.concat(forecast_dfs, ignore_index=True)
    
    # Add temporal features required for SageMaker DeepAR (matching notebook implementation)
    forecast_df['day_of_week'] = forecast_df['timestamp'].dt.dayofweek
    forecast_df['month'] = forecast_df['timestamp'].dt.month
    
    # Sort by item_id and timestamp for proper time series format
    forecast_df = forecast_df.sort_values(['item_id', 'timestamp']).reset_index(drop=True)
    
    return forecast_df

def create_product_lookup_table(df):
    """Create a lookup table for product information matching notebook schema"""
    logger.info("Creating product lookup table...")
    
    # Handle different column names for product information
    product_cols = ['ProductID']
    product_name_col = None
    category_name_col = None
    vendor_name_col = None
    
    if 'ProductDescription' in df.columns:
        product_cols.append('ProductDescription')
        product_name_col = 'ProductDescription'
    elif 'ProductName' in df.columns:
        product_cols.append('ProductName')
        product_name_col = 'ProductName'
    
    if 'ProductCategory' in df.columns:
        product_cols.append('ProductCategory')
        category_name_col = 'ProductCategory'
    elif 'CategoryName' in df.columns:
        product_cols.append('CategoryName')
        category_name_col = 'CategoryName'
    
    if 'VendorName' in df.columns:
        product_cols.append('VendorName')
        vendor_name_col = 'VendorName'
    
    # Create basic product lookup with standardized column names
    product_lookup = df[product_cols].drop_duplicates()
    
    # Standardize column names to match notebook schema
    rename_dict = {'ProductID': 'ProductID'}
    if product_name_col:
        rename_dict[product_name_col] = 'ProductName'
    if category_name_col:
        rename_dict[category_name_col] = 'CategoryName'
    if vendor_name_col:
        rename_dict[vendor_name_col] = 'vendorName'
    
    product_lookup = product_lookup.rename(columns=rename_dict)
    
    # Add missing columns with default values if not present
    if 'ProductName' not in product_lookup.columns:
        product_lookup['ProductName'] = 'Product ' + product_lookup['ProductID'].astype(str)
    if 'CategoryName' not in product_lookup.columns:
        product_lookup['CategoryName'] = 'General'
    if 'vendorName' not in product_lookup.columns:
        product_lookup['vendorName'] = 'Vendor' + product_lookup['ProductID'].astype(str).str.replace('PROD', '')
    
    # Create customer-product relationships matching notebook schema
    # Use OrderUnits if available, otherwise count occurrences
    if 'OrderUnits' in df.columns:
        customer_products = df.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg({
            'OrderUnits': 'count',  # Number of order lines
            'CreateDate': ['min', 'max']  # First and last order dates
        }).reset_index()
        customer_products.columns = ['CustomerID', 'FacilityID', 'ProductID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate']
    else:
        customer_products = df.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg({
            'CreateDate': ['count', 'min', 'max']  # Count, first and last order dates
        }).reset_index()
        customer_products.columns = ['CustomerID', 'FacilityID', 'ProductID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate']
    
    # Merge with product info to create customer-product lookup matching notebook schema
    customer_product_lookup = customer_products.merge(product_lookup, on='ProductID', how='left')
    
    # Ensure proper data types for dates
    customer_product_lookup['FirstOrderDate'] = pd.to_datetime(customer_product_lookup['FirstOrderDate'])
    customer_product_lookup['LastOrderDate'] = pd.to_datetime(customer_product_lookup['LastOrderDate'])
    
    # Reorder columns to match notebook schema exactly
    # Schema: ProductID, ProductName, CategoryName, vendorName, CustomerID, FacilityID, OrderCount, FirstOrderDate, LastOrderDate
    customer_product_lookup = customer_product_lookup[[
        'ProductID', 'ProductName', 'CategoryName', 'vendorName', 
        'CustomerID', 'FacilityID', 'OrderCount', 'FirstOrderDate', 'LastOrderDate'
    ]]
    
    logger.info(f"Created product lookup with {len(product_lookup)} unique products")
    logger.info(f"Created customer-product lookup with {len(customer_product_lookup)} relationships")
    
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

def save_lookup_tables_to_dynamodb(product_lookup, customer_product_lookup):
    """Save lookup tables to DynamoDB"""
    logger.info("Saving lookup tables to DynamoDB...")
    
    try:
        # Use the single ProductLookupTable for all data
        product_table = dynamodb.Table(product_lookup_table)
        
        # Save product lookup data with correct key names
        with product_table.batch_writer() as batch:
            for _, row in product_lookup.iterrows():
                item = {
                    'product_id': str(row['ProductID']),  # Match DynamoDB schema
                    'record_type': 'PRODUCT',  # Distinguish record types
                    'product_name': str(row['ProductName']),
                    'category_name': str(row['CategoryName']),
                    'vendor_name': str(row['vendorName'])
                }
                batch.put_item(Item=item)
        
        logger.info(f"Saved {len(product_lookup)} product records to DynamoDB")
        
        # Save customer-product lookup data with correct key names
        with product_table.batch_writer() as batch:
            for _, row in customer_product_lookup.iterrows():
                # Create composite key for customer-product relationships
                customer_facility_key = f"{row['CustomerID']}#{row['FacilityID']}"
                product_customer_key = f"{row['ProductID']}#{customer_facility_key}"
                
                item = {
                    'product_id': product_customer_key,  # Composite key for uniqueness
                    'customer_facility': customer_facility_key,  # GSI key
                    'record_type': 'CUSTOMER_PRODUCT',  # Distinguish record types
                    'customer_id': str(row['CustomerID']),
                    'facility_id': str(row['FacilityID']),
                    'base_product_id': str(row['ProductID']),
                    'product_name': str(row['ProductName']),
                    'category_name': str(row['CategoryName']),
                    'vendor_name': str(row['vendorName']),
                    'order_count': int(row['OrderCount']),
                    'first_order_date': row['FirstOrderDate'].isoformat(),
                    'last_order_date': row['LastOrderDate'].isoformat()
                }
                batch.put_item(Item=item)
        
        logger.info(f"Saved {len(customer_product_lookup)} customer-product records to DynamoDB")
        
    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {str(e)}")
        # Don't fail the entire process if DynamoDB save fails
        pass

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
            'Quantity': 'Quantity',
            # Handle new data format
            'ProductName': 'ProductDescription',
            'CategoryName': 'ProductCategory',
            'Price': 'UnitPrice',
            'VendorName': 'VendorName'
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
        
        # Flexible date parsing with detailed logging
        logger.info(f"Sample CreateDate values: {df['CreateDate'].head().tolist()}")
        try:
            df['CreateDate'] = pd.to_datetime(df['CreateDate'], infer_datetime_format=True)
            logger.info("Successfully parsed dates using infer_datetime_format")
        except Exception as e:
            logger.warning(f"infer_datetime_format failed: {str(e)}")
            # Try multiple date formats
            date_formats = ['%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d']
            parsed = False
            for fmt in date_formats:
                try:
                    df['CreateDate'] = pd.to_datetime(df['CreateDate'], format=fmt)
                    logger.info(f"Successfully parsed dates using format: {fmt}")
                    parsed = True
                    break
                except Exception as fmt_error:
                    logger.debug(f"Format {fmt} failed: {str(fmt_error)}")
                    continue
            
            if not parsed:
                # If all formats fail, use pandas' flexible parser
                logger.warning("All specific formats failed, using flexible parser")
                df['CreateDate'] = pd.to_datetime(df['CreateDate'], errors='coerce')
                
        # Check for any failed date conversions
        null_dates = df['CreateDate'].isnull().sum()
        if null_dates > 0:
            logger.warning(f"Found {null_dates} rows with unparseable dates")

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
        
        # Save lookup tables to DynamoDB as well
        save_lookup_tables_to_dynamodb(product_lookup, customer_product_lookup)
        
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
