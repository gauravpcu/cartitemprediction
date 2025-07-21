import json
import csv
import os
import logging
import urllib.parse
import gc
import time
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

def calculate_product_demand_patterns(df, max_products=None, batch_size=1000, timeout_seconds=300):
    """Calculate product-specific demand patterns for individual products with batching"""
    start_time = time.time()
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
    
    # Get unique product combinations
    unique_combinations = product_daily[['CustomerID', 'FacilityID', 'ProductID']].drop_duplicates()
    total_combinations = len(unique_combinations)
    
    # Apply limits for large datasets
    if max_products and total_combinations > max_products:
        logger.warning(f"Dataset has {total_combinations} product combinations, limiting to {max_products}")
        unique_combinations = unique_combinations.head(max_products)
    
    logger.info(f"Processing {len(unique_combinations)} product combinations in batches of {batch_size}")
    
    # Use vectorized operations where possible
    product_features = []
    
    # Process in batches to avoid memory issues
    for i in range(0, len(unique_combinations), batch_size):
        batch_combinations = unique_combinations.iloc[i:i+batch_size]
        batch_num = i//batch_size + 1
        total_batches = (len(unique_combinations)-1)//batch_size + 1
        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_combinations)} combinations)")
        
        for _, row in batch_combinations.iterrows():
            # Check for timeout
            if time.time() - start_time > timeout_seconds:
                logger.warning(f"Timeout reached after {timeout_seconds} seconds, processed {len(product_features)} patterns")
                break
                
            customer_id, facility_id, product_id = row['CustomerID'], row['FacilityID'], row['ProductID']
            
            # Filter data for this specific combination
            group = product_daily[
                (product_daily['CustomerID'] == customer_id) & 
                (product_daily['FacilityID'] == facility_id) & 
                (product_daily['ProductID'] == product_id)
            ].copy()
            
            if group.empty:
                continue
                
            # Sort by date once
            group = group.sort_values('Date')
            quantities = group['Quantity'].values
            
            # Safety check for quantities
            if quantities is None or len(quantities) == 0:
                logger.warning(f"Empty quantities for product {product_id}, skipping")
                continue
            
            # Calculate basic statistics using numpy for speed
            total_orders = len(quantities)
            avg_quantity = np.mean(quantities)
            std_quantity = np.std(quantities) if total_orders > 1 else 0
            max_quantity = np.max(quantities)
            min_quantity = np.min(quantities)
            median_quantity = np.median(quantities)
            
            # Calculate order frequency (days between orders)
            if total_orders > 1:
                first_date = pd.to_datetime(group['Date'].iloc[0])
                last_date = pd.to_datetime(group['Date'].iloc[-1])
                date_range = (last_date - first_date).days
                avg_days_between_orders = date_range / (total_orders - 1) if total_orders > 1 else np.nan
            else:
                avg_days_between_orders = np.nan
            
            # Calculate coefficient of variation (volatility measure)
            cv = std_quantity / avg_quantity if avg_quantity > 0 else 0
            
            # Calculate trend (simple linear trend over time) - simplified
            if total_orders > 2:
                # Use simple index-based trend instead of datetime conversion
                x = np.arange(total_orders)
                trend_slope = np.polyfit(x, quantities, 1)[0]
            else:
                trend_slope = 0
            
            # Get product info with fallback names (use first row)
            first_row = group.iloc[0]
            product_name = ''
            if 'ProductDescription' in group.columns:
                product_name = first_row['ProductDescription']
            elif 'ProductName' in group.columns:
                product_name = first_row['ProductName']
            
            category_name = ''
            if 'ProductCategory' in group.columns:
                category_name = first_row['ProductCategory']
            elif 'CategoryName' in group.columns:
                category_name = first_row['CategoryName']
            
            vendor_name = ''
            if 'VendorName' in group.columns:
                vendor_name = first_row['VendorName']
            
            # Get first and last order dates
            first_order_date = group['Date'].iloc[0]
            last_order_date = group['Date'].iloc[-1]
            
            product_features.append({
                'CustomerID': customer_id,
                'FacilityID': facility_id,
                'ProductID': product_id,
                'ProductName': product_name,
                'CategoryName': category_name,
                'VendorName': vendor_name,
                'TotalOrders': total_orders,
                'AvgQuantity': avg_quantity,
                'StdQuantity': std_quantity,
                'MaxQuantity': max_quantity,
                'MinQuantity': min_quantity,
                'MedianQuantity': median_quantity,
                'CoefficientOfVariation': cv,
                'TrendSlope': trend_slope,
                'AvgDaysBetweenOrders': avg_days_between_orders,
                'FirstOrderDate': first_order_date,
                'LastOrderDate': last_order_date
            })
        
        # Force garbage collection after each batch to free memory
        if batch_num % 5 == 0:  # Every 5 batches
            gc.collect()
            logger.info(f"Completed batch {batch_num}, running garbage collection")
        
        # Check for timeout between batches
        if time.time() - start_time > timeout_seconds:
            logger.warning(f"Timeout reached after {timeout_seconds} seconds, processed {len(product_features)} patterns")
            break
    
    logger.info(f"Completed processing {len(product_features)} product patterns")
    return pd.DataFrame(product_features)

def calculate_product_demand_patterns_simple(df):
    """Simplified product demand patterns calculation for very large datasets"""
    logger.info("Calculating simplified product demand patterns for large dataset...")
    
    # Limit to essential columns only to save memory
    essential_cols = ['CustomerID', 'FacilityID', 'ProductID', 'CreateDate']
    if 'Quantity' in df.columns:
        essential_cols.append('Quantity')
    elif 'OrderUnits' in df.columns:
        essential_cols.append('OrderUnits')
    
    # Work with subset of data
    df_subset = df[essential_cols].copy()
    
    # Use aggregation functions directly instead of iterating through groups
    if 'OrderUnits' in df_subset.columns:
        agg_dict = {
            'OrderUnits': ['count', 'sum', 'mean', 'std', 'min', 'max'],
            'CreateDate': ['min', 'max']
        }
    elif 'Quantity' in df_subset.columns:
        agg_dict = {
            'Quantity': ['count', 'sum', 'mean', 'std', 'min', 'max'],
            'CreateDate': ['min', 'max']
        }
    else:
        # Create a quantity column for counting
        df_subset['_count'] = 1
        agg_dict = {
            '_count': ['count', 'sum', 'mean', 'std', 'min', 'max'],
            'CreateDate': ['min', 'max']
        }
    
    # Group and aggregate in one operation
    logger.info("Performing aggregation...")
    product_stats = df_subset.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg(agg_dict).reset_index()
    
    # Clean up subset to free memory
    del df_subset
    gc.collect()
    
    # Flatten column names
    product_stats.columns = ['CustomerID', 'FacilityID', 'ProductID', 
                           'TotalOrders', 'TotalQuantity', 'AvgQuantity', 'StdQuantity',
                           'MinQuantity', 'MaxQuantity',
                           'FirstOrderDate', 'LastOrderDate']
    
    # Fill NaN values
    product_stats['StdQuantity'] = product_stats['StdQuantity'].fillna(0)
    
    # Calculate coefficient of variation (simplified)
    product_stats['CoefficientOfVariation'] = product_stats['StdQuantity'] / product_stats['AvgQuantity']
    product_stats['CoefficientOfVariation'] = product_stats['CoefficientOfVariation'].fillna(0)
    
    # Calculate days between orders (simplified)
    try:
        product_stats['FirstOrderDate'] = pd.to_datetime(product_stats['FirstOrderDate'])
        product_stats['LastOrderDate'] = pd.to_datetime(product_stats['LastOrderDate'])
        product_stats['DateRange'] = (product_stats['LastOrderDate'] - product_stats['FirstOrderDate']).dt.days
        product_stats['AvgDaysBetweenOrders'] = product_stats['DateRange'] / (product_stats['TotalOrders'] - 1)
        product_stats['AvgDaysBetweenOrders'] = product_stats['AvgDaysBetweenOrders'].fillna(0)
    except:
        product_stats['AvgDaysBetweenOrders'] = 0
    
    # Add missing columns with defaults (memory efficient)
    product_stats['MedianQuantity'] = product_stats['AvgQuantity']  # Approximation
    product_stats['TrendSlope'] = 0
    product_stats['ProductName'] = 'Product ' + product_stats['ProductID'].astype(str)
    product_stats['CategoryName'] = 'General'
    product_stats['VendorName'] = 'Vendor' + product_stats['ProductID'].astype(str).str.replace('PROD', '', regex=False)
    
    # Select final columns
    final_columns = ['CustomerID', 'FacilityID', 'ProductID', 'ProductName', 'CategoryName', 'VendorName',
                    'TotalOrders', 'AvgQuantity', 'StdQuantity', 'MaxQuantity', 'MinQuantity', 'MedianQuantity',
                    'CoefficientOfVariation', 'TrendSlope', 'AvgDaysBetweenOrders', 'FirstOrderDate', 'LastOrderDate']
    
    result = product_stats[final_columns].copy()
    
    # Clean up
    del product_stats
    gc.collect()
    
    # Ensure we return a valid DataFrame
    if result is None or result.empty:
        logger.warning("Result is empty, creating placeholder DataFrame")
        result = pd.DataFrame({
            'CustomerID': ['PLACEHOLDER'],
            'FacilityID': ['PLACEHOLDER'],
            'ProductID': ['PLACEHOLDER'],
            'ProductName': ['Placeholder Product'],
            'CategoryName': ['General'],
            'VendorName': ['Placeholder Vendor'],
            'TotalOrders': [1],
            'AvgQuantity': [1.0],
            'StdQuantity': [0.0],
            'MaxQuantity': [1.0],
            'MinQuantity': [1.0],
            'MedianQuantity': [1.0],
            'CoefficientOfVariation': [0.0],
            'TrendSlope': [0.0],
            'AvgDaysBetweenOrders': [0.0],
            'FirstOrderDate': [pd.Timestamp.now()],
            'LastOrderDate': [pd.Timestamp.now()]
        })
    
    logger.info(f"Completed simplified processing for {len(result)} product patterns")
    return result

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
    
    # Log available columns for debugging
    logger.info(f"Available columns: {list(df.columns)}")
    
    # Handle different column names for product information
    product_cols = ['ProductID']
    product_name_col = None
    category_name_col = None
    vendor_name_col = None
    
    # Check for product name columns
    for col_name in ['ProductDescription', 'ProductName', 'Productdescription', 'Productname']:
        if col_name in df.columns:
            product_cols.append(col_name)
            product_name_col = col_name
            break
    
    # Check for category columns
    for col_name in ['ProductCategory', 'CategoryName', 'Productcategory', 'Categoryname']:
        if col_name in df.columns:
            product_cols.append(col_name)
            category_name_col = col_name
            break
    
    # Check for vendor columns
    for col_name in ['VendorName', 'Vendorname']:
        if col_name in df.columns:
            product_cols.append(col_name)
            vendor_name_col = col_name
            break
    
    # Ensure we have at least ProductID
    if 'ProductID' not in df.columns:
        # Try alternative names
        for col_name in ['Productid', 'ProductId', 'PRODUCTID']:
            if col_name in df.columns:
                product_cols = [col_name] + [col for col in product_cols if col != 'ProductID']
                break
        else:
            logger.error("No ProductID column found")
            raise ValueError("ProductID column is required")
    
    # Create basic product lookup with available columns only
    available_cols = [col for col in product_cols if col in df.columns]
    logger.info(f"Using columns for product lookup: {available_cols}")
    
    product_lookup = df[available_cols].drop_duplicates()
    
    # Standardize column names to match notebook schema
    rename_dict = {}
    
    # Find the actual ProductID column name
    product_id_col = 'ProductID'
    for col in product_lookup.columns:
        if col.lower().replace('_', '') == 'productid':
            product_id_col = col
            break
    
    if product_id_col != 'ProductID':
        rename_dict[product_id_col] = 'ProductID'
    
    if product_name_col and product_name_col in product_lookup.columns:
        rename_dict[product_name_col] = 'ProductName'
    if category_name_col and category_name_col in product_lookup.columns:
        rename_dict[category_name_col] = 'CategoryName'
    if vendor_name_col and vendor_name_col in product_lookup.columns:
        rename_dict[vendor_name_col] = 'vendorName'
    
    if rename_dict:
        product_lookup = product_lookup.rename(columns=rename_dict)
    
    # Add missing columns with default values if not present
    if 'ProductName' not in product_lookup.columns:
        product_lookup['ProductName'] = 'Product ' + product_lookup['ProductID'].astype(str)
    if 'CategoryName' not in product_lookup.columns:
        product_lookup['CategoryName'] = 'General'
    if 'vendorName' not in product_lookup.columns:
        product_lookup['vendorName'] = 'Vendor' + product_lookup['ProductID'].astype(str).str.replace('PROD', '', regex=False)
    
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
        
        # Ensure product_lookup is deduplicated by ProductID
        product_lookup_dedup = product_lookup.drop_duplicates(subset=['ProductID'])
        logger.info(f"Deduplicated product lookup: {len(product_lookup)} -> {len(product_lookup_dedup)} records")
        
        # Save product lookup data with correct key names
        saved_product_ids = set()
        with product_table.batch_writer() as batch:
            for _, row in product_lookup_dedup.iterrows():
                product_id = str(row['ProductID'])
                
                # Skip if we've already processed this product_id
                if product_id in saved_product_ids:
                    continue
                    
                item = {
                    'product_id': product_id,  # Match DynamoDB schema
                    'record_type': 'PRODUCT',  # Distinguish record types
                    'product_name': str(row['ProductName']),
                    'category_name': str(row['CategoryName']),
                    'vendor_name': str(row['vendorName'])
                }
                batch.put_item(Item=item)
                saved_product_ids.add(product_id)
        
        logger.info(f"Saved {len(saved_product_ids)} unique product records to DynamoDB")
        
        # Ensure customer_product_lookup is deduplicated by composite key
        customer_product_lookup_dedup = customer_product_lookup.drop_duplicates(subset=['CustomerID', 'FacilityID', 'ProductID'])
        logger.info(f"Deduplicated customer-product lookup: {len(customer_product_lookup)} -> {len(customer_product_lookup_dedup)} records")
        
        # Save customer-product lookup data with correct key names
        saved_composite_keys = set()
        with product_table.batch_writer() as batch:
            for _, row in customer_product_lookup_dedup.iterrows():
                # Create composite key for customer-product relationships
                customer_facility_key = f"{row['CustomerID']}#{row['FacilityID']}"
                product_customer_key = f"{row['ProductID']}#{customer_facility_key}"
                
                # Skip if we've already processed this composite key
                if product_customer_key in saved_composite_keys:
                    continue
                
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
                saved_composite_keys.add(product_customer_key)
        
        logger.info(f"Saved {len(saved_composite_keys)} unique customer-product records to DynamoDB")
        
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

def get_file_size_mb(file_path):
    """Get file size in MB"""
    return os.path.getsize(file_path) / (1024 * 1024)

def split_large_file_and_process(file_path, max_chunk_rows=50000):
    """Split very large files into smaller files and process them separately"""
    logger.info(f"Splitting large file into chunks of max {max_chunk_rows} rows")
    
    # Get total rows
    total_rows = sum(1 for _ in open(file_path)) - 1  # Subtract header
    logger.info(f"Total rows to process: {total_rows}")
    
    if total_rows <= max_chunk_rows:
        # File is small enough to process normally
        return process_large_file_in_chunks(file_path, chunk_size=10000)
    
    # Split into multiple files and process each
    chunk_results = []
    chunk_number = 0
    
    # Read header
    with open(file_path, 'r') as f:
        header = f.readline().strip()
    
    # Process in chunks
    for chunk in pd.read_csv(file_path, chunksize=max_chunk_rows):
        chunk_number += 1
        logger.info(f"Processing chunk {chunk_number} with {len(chunk)} rows")
        
        # Normalize column names
        chunk.columns = [col.strip().replace(' ', '').replace('_', '').title() for col in chunk.columns]
        col_map = {
            'Customerid': 'CustomerID',
            'Facilityid': 'FacilityID', 
            'Productid': 'ProductID',
            'Productdescription': 'ProductDescription',
            'Productcategory': 'ProductCategory',
            'Createdate': 'CreateDate',
            'Quantity': 'Quantity',
            'ProductName': 'ProductDescription',
            'CategoryName': 'ProductCategory',
            'Price': 'UnitPrice',
            'VendorName': 'VendorName'
        }
        chunk.rename(columns={k: v for k, v in col_map.items() if k in chunk.columns}, inplace=True)
        
        # Basic date parsing
        try:
            chunk['CreateDate'] = pd.to_datetime(chunk['CreateDate'], infer_datetime_format=True, errors='coerce')
        except:
            chunk['CreateDate'] = pd.to_datetime(chunk['CreateDate'], format='%m/%d/%y', errors='coerce')
        
        # Add basic temporal features
        chunk['Date'] = chunk['CreateDate'].dt.strftime('%Y-%m-%d')
        chunk['OrderYear'] = chunk['CreateDate'].dt.year
        chunk['OrderMonth'] = chunk['CreateDate'].dt.month
        chunk['OrderDayOfWeek'] = chunk['CreateDate'].dt.dayofweek
        
        # Process this chunk using simplified calculation
        chunk_product_features = calculate_product_demand_patterns_simple(chunk)
        chunk_results.append(chunk_product_features)
        
        # Clean up chunk to free memory
        del chunk
        gc.collect()
        
        logger.info(f"Completed chunk {chunk_number}, generated {len(chunk_product_features)} product patterns")
    
    # Combine results from all chunks
    logger.info("Combining results from all chunks...")
    if chunk_results:
        # Combine all chunk results
        combined_features = pd.concat(chunk_results, ignore_index=True)
        
        # Aggregate duplicate product combinations across chunks
        logger.info("Aggregating duplicate products across chunks...")
        final_features = aggregate_chunk_results(combined_features)
        
        # Clean up
        del chunk_results, combined_features
        gc.collect()
        
        logger.info(f"Final combined result: {len(final_features)} unique product patterns")
        return final_features
    else:
        logger.warning("No chunk results found, returning empty DataFrame")
        return pd.DataFrame()

def aggregate_chunk_results(combined_features):
    """Aggregate product features from multiple chunks"""
    logger.info("Aggregating product features across chunks...")
    
    # Group by product combination and aggregate
    groupby_cols = ['CustomerID', 'FacilityID', 'ProductID']
    
    # Aggregate numeric columns
    agg_dict = {
        'TotalOrders': 'sum',
        'AvgQuantity': 'mean',
        'StdQuantity': 'mean',
        'MaxQuantity': 'max',
        'MinQuantity': 'min',
        'MedianQuantity': 'mean',
        'CoefficientOfVariation': 'mean',
        'TrendSlope': 'mean',
        'AvgDaysBetweenOrders': 'mean',
        'FirstOrderDate': 'min',
        'LastOrderDate': 'max'
    }
    
    # Aggregate
    aggregated = combined_features.groupby(groupby_cols).agg(agg_dict).reset_index()
    
    # Add back non-numeric columns (take first occurrence)
    text_cols = ['ProductName', 'CategoryName', 'VendorName']
    for col in text_cols:
        if col in combined_features.columns:
            text_data = combined_features.groupby(groupby_cols)[col].first().reset_index()
            aggregated = aggregated.merge(text_data, on=groupby_cols, how='left')
    
    # Reorder columns to match expected format
    final_columns = ['CustomerID', 'FacilityID', 'ProductID', 'ProductName', 'CategoryName', 'VendorName',
                    'TotalOrders', 'AvgQuantity', 'StdQuantity', 'MaxQuantity', 'MinQuantity', 'MedianQuantity',
                    'CoefficientOfVariation', 'TrendSlope', 'AvgDaysBetweenOrders', 'FirstOrderDate', 'LastOrderDate']
    
    return aggregated[final_columns]

def create_minimal_lookup_from_file(file_path):
    """Create minimal lookup tables by reading file in chunks"""
    logger.info("Creating minimal lookup tables from file chunks...")
    
    product_data = set()
    customer_product_data = []
    
    # Column mapping
    col_map = {
        'Customerid': 'CustomerID',
        'Facilityid': 'FacilityID', 
        'Productid': 'ProductID',
        'Productdescription': 'ProductDescription',
        'Productcategory': 'ProductCategory',
        'Createdate': 'CreateDate',
        'Quantity': 'Quantity',
        'ProductName': 'ProductDescription',
        'CategoryName': 'ProductCategory',
        'Price': 'UnitPrice',
        'VendorName': 'VendorName'
    }
    
    # Process file in small chunks to extract lookup data
    for chunk in pd.read_csv(file_path, chunksize=10000):
        # Normalize column names
        chunk.columns = [col.strip().replace(' ', '').replace('_', '').title() for col in chunk.columns]
        chunk.rename(columns={k: v for k, v in col_map.items() if k in chunk.columns}, inplace=True)
        
        # Extract unique products - handle different column names
        product_cols_for_lookup = ['ProductID']
        product_name_col_lookup = None
        category_col_lookup = None
        
        # Find product name column
        for col_name in ['ProductDescription', 'ProductName', 'Productdescription', 'Productname']:
            if col_name in chunk.columns:
                product_cols_for_lookup.append(col_name)
                product_name_col_lookup = col_name
                break
        
        # Find category column
        for col_name in ['ProductCategory', 'CategoryName', 'Productcategory', 'Categoryname']:
            if col_name in chunk.columns:
                product_cols_for_lookup.append(col_name)
                category_col_lookup = col_name
                break
        
        # Extract unique products with available columns
        available_product_cols = [col for col in product_cols_for_lookup if col in chunk.columns]
        if len(available_product_cols) > 0:
            for _, row in chunk[available_product_cols].drop_duplicates().iterrows():
                product_data.add((
                    row.get('ProductID', ''),
                    row.get(product_name_col_lookup, f"Product {row.get('ProductID', '')}") if product_name_col_lookup else f"Product {row.get('ProductID', '')}",
                    row.get(category_col_lookup, 'General') if category_col_lookup else 'General'
                ))
        
        # Extract customer-product relationships (sample only to save memory)
        sample_size = min(1000, len(chunk))
        chunk_sample = chunk.sample(n=sample_size) if len(chunk) > sample_size else chunk
        
        for _, row in chunk_sample.iterrows():
            customer_product_data.append({
                'CustomerID': row.get('CustomerID', ''),
                'FacilityID': row.get('FacilityID', ''),
                'ProductID': row.get('ProductID', ''),
                'ProductName': row.get(product_name_col_lookup, f"Product {row.get('ProductID', '')}") if product_name_col_lookup else f"Product {row.get('ProductID', '')}",
                'CategoryName': row.get(category_col_lookup, 'General') if category_col_lookup else 'General',
                'vendorName': f"Vendor{str(row.get('ProductID', '')).replace('PROD', '')}",
                'OrderCount': 1,
                'FirstOrderDate': pd.Timestamp.now(),
                'LastOrderDate': pd.Timestamp.now()
            })
        
        # Clean up chunk
        del chunk
        gc.collect()
    
    # Create product lookup DataFrame
    product_lookup = pd.DataFrame(list(product_data), columns=['ProductID', 'ProductName', 'CategoryName'])
    product_lookup['vendorName'] = 'Vendor' + product_lookup['ProductID'].astype(str).str.replace('PROD', '', regex=False)
    
    # Create customer-product lookup DataFrame
    customer_product_lookup = pd.DataFrame(customer_product_data)
    
    # Remove duplicates and aggregate
    if not customer_product_lookup.empty:
        customer_product_lookup = customer_product_lookup.groupby(['CustomerID', 'FacilityID', 'ProductID']).agg({
            'ProductName': 'first',
            'CategoryName': 'first',
            'vendorName': 'first',
            'OrderCount': 'sum',
            'FirstOrderDate': 'min',
            'LastOrderDate': 'max'
        }).reset_index()
    
    # Ensure we return valid DataFrames
    if product_lookup is None or product_lookup.empty:
        logger.warning("product_lookup is empty, creating minimal placeholder")
        product_lookup = pd.DataFrame({
            'ProductID': ['PLACEHOLDER'],
            'ProductName': ['Placeholder Product'],
            'CategoryName': ['General'],
            'vendorName': ['Placeholder Vendor']
        })
    
    if customer_product_lookup is None or customer_product_lookup.empty:
        logger.warning("customer_product_lookup is empty, creating minimal placeholder")
        customer_product_lookup = pd.DataFrame({
            'CustomerID': ['PLACEHOLDER'],
            'FacilityID': ['PLACEHOLDER'],
            'ProductID': ['PLACEHOLDER'],
            'ProductName': ['Placeholder Product'],
            'CategoryName': ['General'],
            'vendorName': ['Placeholder Vendor'],
            'OrderCount': [1],
            'FirstOrderDate': [pd.Timestamp.now()],
            'LastOrderDate': [pd.Timestamp.now()]
        })
    
    logger.info(f"Created minimal lookup with {len(product_lookup)} products and {len(customer_product_lookup)} relationships")
    
    return product_lookup, customer_product_lookup

def process_large_file_in_chunks(file_path, chunk_size=10000):
    """Process large CSV files in chunks to avoid memory issues"""
    logger.info(f"Processing file in chunks of {chunk_size} rows")
    
    # First pass: get basic info and determine processing strategy
    first_chunk = pd.read_csv(file_path, nrows=1000)
    logger.info(f"Sample columns: {list(first_chunk.columns)}")
    
    # Normalize column names for the sample
    first_chunk.columns = [col.strip().replace(' ', '').replace('_', '').title() for col in first_chunk.columns]
    col_map = {
        'Customerid': 'CustomerID',
        'Facilityid': 'FacilityID', 
        'Productid': 'ProductID',
        'Productdescription': 'ProductDescription',
        'Productcategory': 'ProductCategory',
        'Createdate': 'CreateDate',
        'Quantity': 'Quantity',
        'ProductName': 'ProductDescription',
        'CategoryName': 'ProductCategory',
        'Price': 'UnitPrice',
        'VendorName': 'VendorName'
    }
    first_chunk.rename(columns={k: v for k, v in col_map.items() if k in first_chunk.columns}, inplace=True)
    
    # Determine total rows
    total_rows = sum(1 for _ in open(file_path)) - 1  # Subtract header
    logger.info(f"Total rows to process: {total_rows}")
    
    # Process in chunks and aggregate results
    all_chunks = []
    processed_rows = 0
    
    for chunk in pd.read_csv(file_path, chunksize=chunk_size):
        # Normalize column names
        chunk.columns = [col.strip().replace(' ', '').replace('_', '').title() for col in chunk.columns]
        chunk.rename(columns={k: v for k, v in col_map.items() if k in chunk.columns}, inplace=True)
        
        # Basic date parsing (simplified)
        try:
            chunk['CreateDate'] = pd.to_datetime(chunk['CreateDate'], infer_datetime_format=True, errors='coerce')
        except:
            chunk['CreateDate'] = pd.to_datetime(chunk['CreateDate'], format='%m/%d/%y', errors='coerce')
        
        # Add basic temporal features only
        chunk['Date'] = chunk['CreateDate'].dt.strftime('%Y-%m-%d')
        chunk['OrderYear'] = chunk['CreateDate'].dt.year
        chunk['OrderMonth'] = chunk['CreateDate'].dt.month
        chunk['OrderDayOfWeek'] = chunk['CreateDate'].dt.dayofweek
        
        all_chunks.append(chunk)
        processed_rows += len(chunk)
        
        logger.info(f"Processed {processed_rows}/{total_rows} rows ({processed_rows/total_rows*100:.1f}%)")
        
        # Memory management - don't let chunks accumulate too much
        if len(all_chunks) >= 3:  # Reduced from 5 to 3
            combined = pd.concat(all_chunks, ignore_index=True)
            all_chunks = [combined]
            gc.collect()
    
    # Final combination
    if len(all_chunks) > 1:
        final_df = pd.concat(all_chunks, ignore_index=True)
    else:
        final_df = all_chunks[0] if all_chunks else pd.DataFrame()
    
    logger.info(f"Final dataset size: {len(final_df)} rows")
    return final_df

def lambda_handler(event, context):
    """Lambda function handler to process S3 data and create lookups"""
    try:
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
        
        logger.info(f"Processing file {key} from bucket {bucket}")
        
        download_path = f'/tmp/{os.path.basename(key)}'
        s3_client.download_file(bucket, key, download_path)
        
        # Check file size to determine processing strategy
        file_size_mb = get_file_size_mb(download_path)
        logger.info(f"File size: {file_size_mb:.2f} MB")
        
        # Initialize variables to avoid NoneType errors
        product_features = None
        product_lookup = None
        customer_product_lookup = None
        product_forecast_df = None
        customer_forecast_df = None
        
        # Process data based on file size with more aggressive chunking
        if file_size_mb > 100:  # Very large files - split and process separately
            logger.info("Very large file detected, using split processing")
            try:
                # For very large files, skip normal DataFrame loading and use split processing
                product_features = split_large_file_and_process(download_path, max_chunk_rows=30000)
                logger.info(f"Split processing completed, got {len(product_features) if product_features is not None else 0} product features")
                
                # Create minimal lookup tables directly from file
                product_lookup, customer_product_lookup = create_minimal_lookup_from_file(download_path)
                logger.info(f"Created lookup tables: {len(product_lookup) if product_lookup is not None else 0} products, {len(customer_product_lookup) if customer_product_lookup is not None else 0} relationships")
                
                # Skip forecast data for very large files
                product_forecast_df = pd.DataFrame({
                    'item_id': ['PLACEHOLDER'],
                    'timestamp': [pd.Timestamp.now()],
                    'target_value': [0]
                })
                customer_forecast_df = pd.DataFrame({
                    'item_id': ['PLACEHOLDER'],
                    'timestamp': [pd.Timestamp.now()],
                    'target_value': [0]
                })
                
                # Skip to saving results
                df = None  # Don't load full dataset
            except Exception as e:
                logger.error(f"Error in split processing: {str(e)}")
                # Initialize with empty DataFrames to avoid None errors
                product_features = pd.DataFrame()
                product_lookup = pd.DataFrame()
                customer_product_lookup = pd.DataFrame()
                product_forecast_df = pd.DataFrame()
                customer_forecast_df = pd.DataFrame()
                df = None
            
        elif file_size_mb > 50:  # Large files - use chunked processing
            logger.info("Large file detected, using chunked processing")
            df = process_large_file_in_chunks(download_path, chunk_size=5000)
        elif file_size_mb > 20:  # Medium files - smaller chunks
            logger.info("Medium file detected, using smaller chunks")
            df = process_large_file_in_chunks(download_path, chunk_size=10000)
        else:  # Small files - normal processing
            df = pd.read_csv(download_path)
            logger.info(f"Loaded {len(df)} rows of data")
            
            # Normalize column names: strip spaces, make consistent case
            df.columns = [col.strip().replace(' ', '').replace('_', '').title() for col in df.columns]
            col_map = {
                'Customerid': 'CustomerID',
                'Facilityid': 'FacilityID',
                'Productid': 'ProductID',
                'Productdescription': 'ProductDescription',
                'Productcategory': 'ProductCategory',
                'Createdate': 'CreateDate',
                'Quantity': 'Quantity',
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

            # Feature engineering for small files only
            df = extract_temporal_features(df)
        
        # Clean up download file immediately
        try:
            os.remove(download_path)
        except:
            pass
        
        # Force garbage collection
        gc.collect()
        
        # Process data based on whether we have a DataFrame or used split processing
        if df is not None:
            # Normal processing path
            data_size = len(df)
            if data_size > 100000:  # For large datasets, use simplified calculation only
                logger.info(f"Large dataset detected ({data_size} rows), using simplified calculation")
                product_features = calculate_product_demand_patterns_simple(df)
            elif data_size > 50000:  # For medium datasets, very limited processing
                max_products = 2000  # Reduced from 5000
                batch_size = 200    # Reduced from 500
                timeout_seconds = 180  # 3 minutes
                logger.info(f"Medium dataset detected ({data_size} rows), limiting to {max_products} products")
                product_features = calculate_product_demand_patterns(df, max_products=max_products, batch_size=batch_size, timeout_seconds=timeout_seconds)
            elif data_size > 20000:  # For smaller medium datasets
                max_products = 5000
                batch_size = 500
                timeout_seconds = 240  # 4 minutes
                product_features = calculate_product_demand_patterns(df, max_products=max_products, batch_size=batch_size, timeout_seconds=timeout_seconds)
            else:  # For smaller datasets
                max_products = None
                batch_size = 1000
                timeout_seconds = 300  # 5 minutes
                product_features = calculate_product_demand_patterns(df, max_products=max_products, batch_size=batch_size, timeout_seconds=timeout_seconds)
            
            # Force garbage collection after heavy processing
            gc.collect()
            
            # Create lookup tables with memory management
            logger.info("Creating lookup tables...")
            product_lookup, customer_product_lookup = create_product_lookup_table(df)
            
            # Force garbage collection
            gc.collect()
            
            # Prepare forecast data at different levels (skip for very large datasets)
            if data_size <= 100000:
                logger.info("Preparing forecast data...")
                product_forecast_df = prepare_product_forecast_data(df)
                customer_forecast_df = prepare_customer_level_forecast_data(df)
            else:
                logger.info("Skipping forecast data preparation for large dataset")
                # Create minimal forecast data
                product_forecast_df = pd.DataFrame({
                    'item_id': ['PLACEHOLDER'],
                    'timestamp': [pd.Timestamp.now()],
                    'target_value': [0]
                })
                customer_forecast_df = pd.DataFrame({
                    'item_id': ['PLACEHOLDER'],
                    'timestamp': [pd.Timestamp.now()],
                    'target_value': [0]
                })
        else:
            # Split processing was used - product_features, product_lookup, customer_product_lookup, 
            # product_forecast_df, and customer_forecast_df are already created
            logger.info("Using results from split processing")
            
            # Ensure variables are not None
            if product_features is None:
                logger.warning("product_features is None, initializing empty DataFrame")
                product_features = pd.DataFrame()
            if product_lookup is None:
                logger.warning("product_lookup is None, initializing empty DataFrame")
                product_lookup = pd.DataFrame()
            if customer_product_lookup is None:
                logger.warning("customer_product_lookup is None, initializing empty DataFrame")
                customer_product_lookup = pd.DataFrame()
            if product_forecast_df is None:
                logger.warning("product_forecast_df is None, initializing empty DataFrame")
                product_forecast_df = pd.DataFrame()
            if customer_forecast_df is None:
                logger.warning("customer_forecast_df is None, initializing empty DataFrame")
                customer_forecast_df = pd.DataFrame()
        
        # Force garbage collection
        gc.collect()
        
        # Save all the processed data
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        
        
        # Save product features
        if product_features is not None and not product_features.empty:
            product_features_file = f'/tmp/product_features_{timestamp}.csv'
            product_features.to_csv(product_features_file, index=False)
            product_features_key = f'processed/{timestamp}/product_features.csv'
            s3_client.upload_file(product_features_file, processed_bucket, product_features_key)
        else:
            logger.warning("Product features is None or empty, skipping save")
            product_features_key = None
        
        # Save product lookup
        if product_lookup is not None and not product_lookup.empty:
            product_lookup_file = f'/tmp/product_lookup_{timestamp}.csv'
            product_lookup.to_csv(product_lookup_file, index=False)
            product_lookup_key = f'lookup/{timestamp}/product_lookup.csv'
            s3_client.upload_file(product_lookup_file, processed_bucket, product_lookup_key)
        else:
            logger.warning("Product lookup is None or empty, skipping save")
            product_lookup_key = None
        
        # Save customer-product lookup
        if customer_product_lookup is not None and not customer_product_lookup.empty:
            customer_product_lookup_file = f'/tmp/customer_product_lookup_{timestamp}.csv'
            customer_product_lookup.to_csv(customer_product_lookup_file, index=False)
            customer_product_lookup_key = f'lookup/{timestamp}/customer_product_lookup.csv'
            s3_client.upload_file(customer_product_lookup_file, processed_bucket, customer_product_lookup_key)
        else:
            logger.warning("Customer product lookup is None or empty, skipping save")
            customer_product_lookup_key = None
        
        # Save product-level forecast data
        if product_forecast_df is not None and not product_forecast_df.empty:
            product_forecast_file = f'/tmp/product_forecast_data_{timestamp}.csv'
            product_forecast_df.to_csv(product_forecast_file, index=False)
            product_forecast_key = f'forecast_format/{timestamp}/product_forecast_data.csv'
            s3_client.upload_file(product_forecast_file, processed_bucket, product_forecast_key)
        else:
            logger.warning("Product forecast data is None or empty, skipping save")
            product_forecast_key = None
        
        # Save customer-level forecast data
        if customer_forecast_df is not None and not customer_forecast_df.empty:
            customer_forecast_file = f'/tmp/customer_forecast_data_{timestamp}.csv'
            customer_forecast_df.to_csv(customer_forecast_file, index=False)
            customer_forecast_key = f'forecast_format/{timestamp}/customer_forecast_data.csv'
            s3_client.upload_file(customer_forecast_file, processed_bucket, customer_forecast_key)
        else:
            logger.warning("Customer forecast data is None or empty, skipping save")
            customer_forecast_key = None
        
        # Save lookup tables to DynamoDB as well
        if product_lookup is not None and customer_product_lookup is not None:
            save_lookup_tables_to_dynamodb(product_lookup, customer_product_lookup)
        else:
            logger.warning("Skipping DynamoDB save due to missing lookup tables")
        
        logger.info(f"Successfully processed and uploaded all data files")
        
        # Determine the number of records processed
        try:
            if df is not None:
                records_processed = len(df)
                logger.info(f"Records processed from df: {records_processed}")
            else:
                # For split processing, use the number of product patterns as a proxy
                if product_features is not None:
                    records_processed = len(product_features)
                    logger.info(f"Records processed from product_features: {records_processed}")
                else:
                    records_processed = 0
                    logger.warning("Both df and product_features are None, setting records_processed to 0")
        except Exception as e:
            logger.error(f"Error determining records processed: {str(e)}")
            records_processed = 0
        
        # Build response body with safe key handling
        try:
            total_products = len(product_lookup) if product_lookup is not None else 0
            logger.info(f"Total unique products: {total_products}")
        except Exception as e:
            logger.error(f"Error getting product_lookup length: {str(e)}")
            total_products = 0
            
        try:
            total_combinations = len(customer_product_lookup) if customer_product_lookup is not None else 0
            logger.info(f"Total customer-product combinations: {total_combinations}")
        except Exception as e:
            logger.error(f"Error getting customer_product_lookup length: {str(e)}")
            total_combinations = 0
        
        response_body = {
            'message': f'Successfully processed {records_processed} records',
            'total_unique_products': total_products,
            'total_customer_product_combinations': total_combinations
        }
        
        # Only add S3 locations if files were actually saved
        if product_features_key:
            response_body['product_features_location'] = f's3://{processed_bucket}/{product_features_key}'
        if product_lookup_key:
            response_body['product_lookup_location'] = f's3://{processed_bucket}/{product_lookup_key}'
        if customer_product_lookup_key:
            response_body['customer_product_lookup_location'] = f's3://{processed_bucket}/{customer_product_lookup_key}'
        if product_forecast_key:
            response_body['product_forecast_location'] = f's3://{processed_bucket}/{product_forecast_key}'
        if customer_forecast_key:
            response_body['customer_forecast_location'] = f's3://{processed_bucket}/{customer_forecast_key}'
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_body)
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
