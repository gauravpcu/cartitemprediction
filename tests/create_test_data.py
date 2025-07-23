#!/usr/bin/env python3
"""
Create test data for the optimized feature engineering function
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

def generate_test_data(num_rows=50000):
    """Generate test dataset"""
    print(f"Generating {num_rows} rows of test data...")
    
    # Generate realistic data
    customers = [f"CUSTOMER_{i:04d}" for i in range(1, 51)]  # 50 customers
    facilities = list(range(1, 101))  # 100 facilities
    products = [f"PROD_{i:05d}" for i in range(1, 1001)]  # 1000 products
    categories = ["Medical", "Surgical", "Pharmacy", "Equipment", "Supplies"]
    
    data = []
    start_date = datetime(2024, 1, 1)
    
    for i in range(num_rows):
        # Generate realistic order data
        order_date = start_date + timedelta(days=random.randint(0, 365))
        
        row = {
            'PortalID': 'HYB',
            'CreateDate': order_date.strftime('%m/%d/%y'),
            'CustomerID': random.choice(customers),
            'FacilityID': random.choice(facilities),
            'ProductID': random.choice(products),
            'Quantity': random.randint(1, 20),
            'UnitPrice': round(random.uniform(1.0, 100.0), 2),
            'OrderID': f"ORD_{i:08d}",
            'CategoryName': random.choice(categories),
            'ProductName': f"Product {random.choice(products)}"
        }
        data.append(row)
        
        if (i + 1) % 10000 == 0:
            print(f"Generated {i + 1} rows...")
    
    df = pd.DataFrame(data)
    return df

def main():
    # Create different sized test files
    sizes = [
        (10000, "test_small_10k.csv"),
        (50000, "test_medium_50k.csv"),
        (100000, "test_large_100k.csv")
    ]
    
    for num_rows, filename in sizes:
        print(f"\nCreating {filename}...")
        df = generate_test_data(num_rows)
        df.to_csv(filename, index=False)
        print(f"Saved {filename} ({len(df)} rows)")
        
        # Show file size
        import os
        size_mb = os.path.getsize(filename) / (1024 * 1024)
        print(f"File size: {size_mb:.2f} MB")

if __name__ == "__main__":
    main()