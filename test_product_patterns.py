#!/usr/bin/env python3

import pandas as pd
import numpy as np
from datetime import datetime

def calculate_product_demand_patterns(df):
    """Calculate product-specific demand patterns for individual products"""
    print("Calculating product demand patterns...")
    
    # Group by customer, facility, product, and date to get daily quantities
    if 'OrderUnits' in df.columns:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date'])['OrderUnits'].sum().reset_index(name='Quantity')
    else:
        product_daily = df.groupby(['CustomerID', 'FacilityID', 'ProductID', 'Date']).size().reset_index(name='Quantity')
    
    # Add product information back
    product_cols = ['ProductID']
    if 'ProductName' in df.columns:
        product_cols.append('ProductName')
    if 'CategoryName' in df.columns:
        product_cols.append('CategoryName')
    if 'VendorName' in df.columns:
        product_cols.append('VendorName')
    
    product_info = df[product_cols].drop_duplicates()
    product_daily = product_daily.merge(product_info, on='ProductID', how='left')
    
    # Calculate product-specific features
    product_groups = product_daily.groupby(['CustomerID', 'FacilityID', 'ProductID'])
    
    product_features = []
    for (customer_id, facility_id, product_id), group in product_groups:
        group_sorted = group.sort_values('Date')
        
        total_orders = len(group_sorted)
        avg_quantity = group_sorted['Quantity'].mean()
        std_quantity = group_sorted['Quantity'].std()
        max_quantity = group_sorted['Quantity'].max()
        min_quantity = group_sorted['Quantity'].min()
        median_quantity = group_sorted['Quantity'].median()
        
        if total_orders > 1:
            date_range = (pd.to_datetime(group_sorted['Date'].max()) - pd.to_datetime(group_sorted['Date'].min())).days
            avg_days_between_orders = date_range / (total_orders - 1) if total_orders > 1 else np.nan
        else:
            avg_days_between_orders = np.nan
        
        cv = std_quantity / avg_quantity if avg_quantity > 0 else 0
        
        if total_orders > 2:
            dates_numeric = pd.to_datetime(group_sorted['Date']).astype(int) / 10**9
            trend_slope = np.polyfit(dates_numeric, group_sorted['Quantity'], 1)[0]
        else:
            trend_slope = 0
        
        product_name = group_sorted['ProductName'].iloc[0] if 'ProductName' in group_sorted.columns else ''
        category_name = group_sorted['CategoryName'].iloc[0] if 'CategoryName' in group_sorted.columns else ''
        vendor_name = group_sorted['VendorName'].iloc[0] if 'VendorName' in group_sorted.columns else ''
        
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

if __name__ == "__main__":
    # Create test data
    test_data = {
        'CustomerID': ['C1', 'C1', 'C1', 'C2', 'C2'],
        'FacilityID': ['F1', 'F1', 'F1', 'F2', 'F2'],
        'ProductID': ['P1', 'P1', 'P2', 'P1', 'P1'],
        'ProductName': ['Product 1', 'Product 1', 'Product 2', 'Product 1', 'Product 1'],
        'CategoryName': ['Cat A', 'Cat A', 'Cat B', 'Cat A', 'Cat A'],
        'VendorName': ['Vendor X', 'Vendor X', 'Vendor Y', 'Vendor X', 'Vendor X'],
        'Date': ['2024-01-01', '2024-01-05', '2024-01-03', '2024-01-02', '2024-01-10'],
        'OrderUnits': [10, 15, 5, 20, 25]
    }

    df = pd.DataFrame(test_data)
    result = calculate_product_demand_patterns(df)
    print('Test successful!')
    print('Columns:', list(result.columns))
    print('Sample result:')
    print(result.head())
    print('\nDetailed results:')
    for idx, row in result.iterrows():
        print(f"Product {row['ProductID']} for Customer {row['CustomerID']}, Facility {row['FacilityID']}:")
        print(f"  - Total Orders: {row['TotalOrders']}")
        print(f"  - Avg Quantity: {row['AvgQuantity']:.2f}")
        print(f"  - Std Quantity: {row['StdQuantity']:.2f}")
        print(f"  - Avg Days Between Orders: {row['AvgDaysBetweenOrders']}")
        print(f"  - Coefficient of Variation: {row['CoefficientOfVariation']:.2f}")
        print()