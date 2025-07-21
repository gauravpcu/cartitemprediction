import json
import os
import logging
import uuid
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

# Use SageMaker client instead of Forecast
sagemaker_runtime_client = boto3.client('sagemaker-runtime')
bedrock_client = boto3.client('bedrock-runtime')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Get environment variables
bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
feedback_table_name = os.environ.get('FEEDBACK_TABLE')
processed_bucket = os.environ.get('PROCESSED_BUCKET')
sagemaker_endpoint_name = os.environ.get('SAGEMAKER_ENDPOINT_NAME')

def get_product_lookup_data():
    """Get product lookup data from S3"""
    try:
        # List objects in the lookup folder to get the latest
        response = s3_client.list_objects_v2(
            Bucket=processed_bucket,
            Prefix='lookup/',
            Delimiter='/'
        )
        
        if 'CommonPrefixes' not in response:
            return pd.DataFrame(), pd.DataFrame()
        
        # Get the latest timestamp folder
        latest_folder = sorted([prefix['Prefix'] for prefix in response['CommonPrefixes']])[-1]
        
        # Download product lookup
        product_lookup_key = f"{latest_folder}product_lookup.csv"
        product_lookup_path = '/tmp/product_lookup.csv'
        s3_client.download_file(processed_bucket, product_lookup_key, product_lookup_path)
        product_lookup_df = pd.read_csv(product_lookup_path)
        
        # Download customer-product lookup
        customer_product_lookup_key = f"{latest_folder}customer_product_lookup.csv"
        customer_product_lookup_path = '/tmp/customer_product_lookup.csv'
        s3_client.download_file(processed_bucket, customer_product_lookup_key, customer_product_lookup_path)
        customer_product_lookup_df = pd.read_csv(customer_product_lookup_path)
        
        return product_lookup_df, customer_product_lookup_df
        
    except Exception as e:
        logger.error(f"Error getting product lookup data: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()

def load_feature_mappings():
    """Load feature mappings from S3 that were created during model training"""
    # Default safe mappings with higher cardinality based on training
    default_mappings = {
        'customer_mapping': {},
        'facility_mapping': {},
        'category_mapping': {},
        'cardinality': [4, 50, 24]  # Updated cardinality from training
    }
    
    try:
        import pickle
        
        # Try to load from S3 (adjust bucket and key as needed)
        bucket = 'sagemaker-us-east-1-533267165065'
        key = 'procurement-partners-hybrent-deepar/feature_mappings/feature_mappings.pkl'
        
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            feature_mappings = pickle.loads(response['Body'].read())
            
            # Validate the mappings
            if not isinstance(feature_mappings, dict):
                logger.warning(f"Invalid feature mappings format: not a dictionary. Using defaults.")
                return default_mappings
                
            # Ensure cardinality exists and is valid
            cardinality = feature_mappings.get('cardinality')
            if not cardinality or not isinstance(cardinality, list) or len(cardinality) < 3:
                logger.warning(f"Invalid cardinality in feature mappings. Using default cardinality.")
                feature_mappings['cardinality'] = default_mappings['cardinality']
            
            # Ensure all required mappings exist
            for key in ['customer_mapping', 'facility_mapping', 'category_mapping']:
                if key not in feature_mappings or not isinstance(feature_mappings[key], dict):
                    logger.warning(f"Missing or invalid {key} in feature mappings. Using empty mapping.")
                    feature_mappings[key] = {}
            
            logger.info(f"Loaded feature mappings from S3 with cardinality: {feature_mappings.get('cardinality')}")
            return feature_mappings
            
        except s3_client.exceptions.NoSuchKey:
            logger.warning(f"Feature mappings file not found in S3. Trying local file.")
            # Try to load from local file as fallback
            try:
                with open('feature_mappings.pkl', 'rb') as f:
                    feature_mappings = pickle.load(f)
                logger.info(f"Loaded feature mappings from local file with cardinality: {feature_mappings.get('cardinality')}")
                return feature_mappings
            except Exception as local_error:
                logger.warning(f"Could not load local feature mappings: {str(local_error)}")
                return default_mappings
            
    except Exception as e:
        logger.warning(f"Could not load feature mappings from S3: {str(e)}")
        return default_mappings

def query_sagemaker_for_predictions(customer_id, facility_id, product_lookup_df, customer_product_lookup_df):
    """Query SageMaker DeepAR endpoint for product-level predictions matching notebook approach"""
    try:
        if not sagemaker_endpoint_name:
            logger.warning("No SageMaker endpoint available, using mock data")
            return generate_mock_product_predictions(customer_id, facility_id, customer_product_lookup_df)
        
        # Load feature mappings from training
        feature_mappings = load_feature_mappings()
        cardinality = feature_mappings.get('cardinality', [4, 4, 4])

        # Log incoming types and values
        logger.info(f"API customer_id: {customer_id} (type: {type(customer_id)})")
        logger.info(f"API facility_id: {facility_id} (type: {type(facility_id)})")

        # Normalize both DataFrame and input to string for robust matching
        customer_product_lookup_df['CustomerID'] = customer_product_lookup_df['CustomerID'].astype(str).str.strip()
        customer_product_lookup_df['FacilityID'] = customer_product_lookup_df['FacilityID'].astype(str).str.strip()
        norm_customer_id = str(customer_id).strip()
        norm_facility_id = str(facility_id).strip()

        # Get products for this customer-facility combination
        customer_products = customer_product_lookup_df[
            (customer_product_lookup_df['CustomerID'] == norm_customer_id) &
            (customer_product_lookup_df['FacilityID'] == norm_facility_id)
        ]
        logger.info(f"Found {len(customer_products)} products for customer {norm_customer_id} at facility {norm_facility_id}")

        if customer_products.empty:
            logger.warning(f"No products found for customer {norm_customer_id} at facility {norm_facility_id} in lookup data.")
            return []

        product_predictions = []
        prediction_length = 14  # Match notebook's prediction length
        
        # Process each product individually (matching notebook approach)
        for _, product_row in customer_products.head(10).iterrows():  # Limit for performance
            try:
                # Create test instance for this product (matching notebook format)
                item_id = f"{product_row['CustomerID']}_{product_row['FacilityID']}_{product_row['ProductID']}"
                
                # Create basic time series data (simplified for Lambda)
                # In production, this would come from historical order data
                base_date = datetime.now() - timedelta(days=28)  # Context length from notebook
                historical_dates = pd.date_range(start=base_date, periods=28, freq='D')
                
                # Generate mock historical target values based on order history
                avg_quantity = max(1, product_row['OrderCount'] // 30)  # Rough daily average
                historical_target = [float(avg_quantity + np.random.normal(0, avg_quantity * 0.2)) for _ in range(28)]
                
                # Create dynamic features (matching notebook approach)
                dynamic_feat = []
                # Day of week feature (normalized 0-1)
                day_of_week_feat = [float(d.dayofweek)/6 for d in historical_dates]
                # Month feature (normalized 0-1) 
                month_feat = [float(d.month-1)/11 for d in historical_dates]
                dynamic_feat = [day_of_week_feat, month_feat]
                
                # Extend dynamic features for prediction period
                future_dates = pd.date_range(start=historical_dates[-1] + timedelta(days=1), periods=prediction_length, freq='D')
                future_day_of_week = [float(d.dayofweek)/6 for d in future_dates]
                future_month = [float(d.month-1)/11 for d in future_dates]
                
                extended_dynamic_feat = [
                    day_of_week_feat + future_day_of_week,
                    month_feat + future_month
                ]
                
                # Create categorical features using training mappings (matching notebook approach)
                customer_mapping = feature_mappings.get('customer_mapping', {})
                facility_mapping = feature_mappings.get('facility_mapping', {})
                category_mapping = feature_mappings.get('category_mapping', {})
                
                # Get categorical values with fallbacks
                customer_id_str = str(product_row['CustomerID'])
                facility_id_str = str(product_row['FacilityID'])
                
                customer_cat = customer_mapping.get(customer_id_str, 0)
                facility_cat = facility_mapping.get(facility_id_str, 0)
                
                # Log mapping attempts for debugging
                logger.info(f"Mapping attempt for product {product_row['ProductID']}: Customer {customer_id_str} -> {customer_cat}, Facility {facility_id_str} -> {facility_cat}")
                
                # For category, try to get from product lookup or use default
                category_name = product_row.get('CategoryName', 'General')
                category_cat = category_mapping.get(category_name, 0)
                
                # Ensure values don't exceed cardinality limits and are valid integers
                try:
                    # Convert to integers first (in case they're strings or other types)
                    customer_cat = int(customer_cat)
                    facility_cat = int(facility_cat)
                    category_cat = int(category_cat)
                    
                    # Ensure they're within cardinality bounds
                    customer_cat = max(0, min(customer_cat, cardinality[0] - 1))
                    facility_cat = max(0, min(facility_cat, cardinality[1] - 1))
                    category_cat = max(0, min(category_cat, cardinality[2] - 1))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error converting categorical features for product {product_row['ProductID']}: {str(e)}")
                    # Use safe defaults
                    customer_cat = 0
                    facility_cat = 0
                    category_cat = 0
                
                cat_features = [customer_cat, facility_cat, category_cat]
                
                logger.info(f"Categorical features for product {product_row['ProductID']}: {cat_features} (cardinality: {cardinality})")
                
                # Create request payload matching notebook format
                request_instance = {
                    "start": base_date.strftime('%Y-%m-%d'),
                    "target": historical_target,
                    "cat": cat_features,
                    "dynamic_feat": extended_dynamic_feat
                }
                
                request_payload = {
                    "instances": [request_instance],
                    "configuration": {
                        "num_samples": 100,
                        "output_types": ["quantiles"],
                        "quantiles": ["0.1", "0.5", "0.9"]
                    }
                }
                
                logger.info(f"Invoking SageMaker endpoint for product {product_row['ProductID']} with cat features: {cat_features}")
                
                try:
                    # Log the full request payload for debugging
                    if product_row['ProductID'] == 15:  # Special logging for problematic product
                        logger.info(f"Full request payload for product 15: {json.dumps(request_payload)}")
                    
                    response = sagemaker_runtime_client.invoke_endpoint(
                        EndpointName=sagemaker_endpoint_name,
                        ContentType='application/json',
                        Body=json.dumps(request_payload)
                    )
                except Exception as sagemaker_error:
                    error_msg = str(sagemaker_error)
                    logger.error(f"Error processing product {product_row['ProductID']}: {error_msg}")
                    
                    # Special handling for cardinality errors
                    if "categorical value" in error_msg and "exceeds cardinality" in error_msg:
                        logger.warning(f"Cardinality error detected for product {product_row['ProductID']}. Using fallback prediction.")
                        # Add this product to a list for future retraining
                        # Skip this product and continue with others
                    
                    # Skip this product and continue with others
                    continue
                
                # Parse response matching notebook approach
                result = json.loads(response['Body'].read().decode())
                logger.info(f"SageMaker response for product {product_row['ProductID']}: {json.dumps(result, indent=2)}")
                
                predictions_data = result['predictions'][0]
                logger.info(f"Predictions data for product {product_row['ProductID']}: {json.dumps(predictions_data, indent=2)}")
                
                # Extract quantiles (matching notebook format)
                p10_values = predictions_data['quantiles']['0.1']
                p50_values = predictions_data['quantiles']['0.5'] 
                p90_values = predictions_data['quantiles']['0.9']
                
                logger.info(f"Extracted quantiles for product {product_row['ProductID']}: p10={len(p10_values)} values, p50={len(p50_values)} values, p90={len(p90_values)} values")
                
                # Format predictions by date (matching notebook output)
                predictions = {}
                for i in range(min(len(p50_values), prediction_length)):
                    pred_date = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
                    predictions[pred_date] = {
                        'p10': float(p10_values[i]),
                        'p50': float(p50_values[i]),
                        'p90': float(p90_values[i]),
                        'mean': float(p50_values[i])  # Use p50 as mean
                    }
                
                logger.info(f"Formatted predictions for product {product_row['ProductID']}: {len(predictions)} days of predictions")
                logger.info(f"Sample prediction for product {product_row['ProductID']}: {list(predictions.items())[0] if predictions else 'No predictions'}")
                
                product_predictions.append({
                    'product_id': product_row['ProductID'],
                    'product_name': product_row['ProductName'],
                    'category_name': product_row['CategoryName'],
                    'vendor_name': product_row['vendorName'],
                    'predictions': predictions,
                    'order_history': {
                        'order_count': product_row['OrderCount'],
                        'first_order': product_row['FirstOrderDate'],
                        'last_order': product_row['LastOrderDate']
                    }
                })
                
            except Exception as product_error:
                logger.error(f"Error processing product {product_row['ProductID']}: {str(product_error)}")
                # Generate mock prediction for this product when SageMaker fails
                logger.info(f"Generating mock prediction for product {product_row['ProductID']}")
                
                # Generate mock predictions for next 7 days
                mock_predictions = {}
                base_date = datetime.now()
                base_quantity = max(1, product_row['OrderCount'])
                
                for i in range(7):
                    pred_date = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
                    mock_predictions[pred_date] = {
                        'p10': max(0, base_quantity * 0.5),
                        'p50': base_quantity,
                        'p90': base_quantity * 2,
                        'mean': base_quantity
                    }
                
                product_predictions.append({
                    'product_id': product_row['ProductID'],
                    'product_name': product_row['ProductName'],
                    'category_name': product_row['CategoryName'],
                    'vendor_name': product_row['vendorName'],
                    'predictions': mock_predictions,
                    'order_history': {
                        'order_count': product_row['OrderCount'],
                        'first_order': product_row['FirstOrderDate'],
                        'last_order': product_row['LastOrderDate']
                    },
                    'mock_data': True  # Flag to indicate this is mock data
                })
                continue

        return product_predictions

    except Exception as e:
        logger.error(f"Error querying SageMaker for predictions: {str(e)}")
        return generate_mock_product_predictions(customer_id, facility_id, customer_product_lookup_df)

def generate_mock_product_predictions(customer_id, facility_id, customer_product_lookup_df):
    """Generate mock product predictions for testing"""
    try:
        # Log incoming types and values for debugging
        logger.info(f"MOCK: API customer_id: {customer_id} (type: {type(customer_id)})")
        logger.info(f"MOCK: API facility_id: {facility_id} (type: {type(facility_id)})")

        # Normalize both DataFrame and input to string for robust matching
        customer_product_lookup_df['CustomerID'] = customer_product_lookup_df['CustomerID'].astype(str).str.strip()
        customer_product_lookup_df['FacilityID'] = customer_product_lookup_df['FacilityID'].astype(str).str.strip()
        norm_customer_id = str(customer_id).strip()
        norm_facility_id = str(facility_id).strip()

        logger.info(f"MOCK: Normalized API customer_id: {norm_customer_id}")
        logger.info(f"MOCK: Normalized API facility_id: {norm_facility_id}")
        logger.info(f"MOCK: Unique CustomerIDs in lookup: {customer_product_lookup_df['CustomerID'].unique()}")
        logger.info(f"MOCK: Unique FacilityIDs in lookup: {customer_product_lookup_df['FacilityID'].unique()}")

        # Get products for this customer-facility combination
        customer_products = customer_product_lookup_df[
            (customer_product_lookup_df['CustomerID'] == norm_customer_id) & 
            (customer_product_lookup_df['FacilityID'] == norm_facility_id)
        ]
        
        logger.info(f"MOCK: Found {len(customer_products)} products for customer {norm_customer_id} at facility {norm_facility_id}")
        
        product_predictions = []
        base_date = datetime.now()
        
        for _, product_row in customer_products.head(10).iterrows():  # Limit to top 10 for demo
            # Generate mock predictions for next 7 days
            mock_predictions = {}
            for i in range(7):
                pred_date = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
                # Generate realistic quantities based on order history
                base_quantity = max(1, product_row['OrderCount'] // 10)
                mock_predictions[pred_date] = {
                    'p10': max(0, base_quantity * 0.5),
                    'p50': base_quantity,
                    'p90': base_quantity * 2,
                    'mean': base_quantity
                }
            
            product_predictions.append({
                'product_id': product_row['ProductID'],
                'product_name': product_row['ProductName'],
                'category_name': product_row['CategoryName'],
                'vendor_name': product_row['vendorName'],
                'predictions': mock_predictions,
                'order_history': {
                    'order_count': product_row['OrderCount'],
                    'first_order': product_row['FirstOrderDate'],
                    'last_order': product_row['LastOrderDate']
                }
            })
        
        return product_predictions
        
    except Exception as e:
        logger.error(f"Error generating mock predictions: {str(e)}")
        return []

def call_bedrock_for_product_recommendations(product_predictions, customer_id, facility_id):
    """Call Amazon Bedrock to generate product recommendations and insights matching notebook approach"""
    try:
        logger.info(f"Calling Bedrock for customer {customer_id}, facility {facility_id}")
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Prepare product data for Bedrock matching notebook format
        bedrock_product_data = []
        
        for pred in product_predictions[:10]:  # Limit to top 10 for prompt size
            # Calculate statistics matching notebook approach
            predictions = pred['predictions']
            if predictions:
                # Extract p50 values for analysis
                p50_values = [day_pred.get('p50', 0) for day_pred in predictions.values()]
                p10_values = [day_pred.get('p10', 0) for day_pred in predictions.values()]
                p90_values = [day_pred.get('p90', 0) for day_pred in predictions.values()]
                
                # Calculate metrics matching notebook
                avg_quantity = float(np.mean(p50_values)) if p50_values else 0
                trend = "increasing" if len(p50_values) > 1 and p50_values[-1] > p50_values[0] else "decreasing"
                volatility = float(np.std(p50_values)) if len(p50_values) > 1 else 0
                
                # Calculate confidence score (inverse of confidence interval width)
                confidence_width = float(np.mean(np.array(p90_values) - np.array(p10_values))) if p90_values and p10_values else 0
                confidence_score = max(0, min(100, 100 - (confidence_width / avg_quantity * 100))) if avg_quantity > 0 else 50
                
                bedrock_product_data.append({
                    'product_name': pred['product_name'],
                    'product_id': pred['product_id'],
                    'category': pred['category_name'],
                    'predicted_avg': avg_quantity,
                    'p10_avg': float(np.mean(p10_values)) if p10_values else 0,
                    'p50_avg': float(np.mean(p50_values)) if p50_values else 0,
                    'p90_avg': float(np.mean(p90_values)) if p90_values else 0,
                    'trend': trend,
                    'volatility': volatility,
                    'confidence_score': confidence_score,
                    'historical_orders': pred['order_history']['order_count']
                })
        
        logger.info(f"Prepared {len(bedrock_product_data)} products for Bedrock analysis")
        
        # Create prompt matching notebook format
        prompt = f"""
        Based on the following product-level demand forecasts:
        
        Current date: {current_date}
        Product predictions: {json.dumps(bedrock_product_data, indent=2)}
        
        Please provide intuitive business insights and actionable recommendations for procurement planning.
        
        For each product, consider:
        1. The predicted demand (p50_avg)
        2. The confidence in the prediction (confidence_score)
        3. The trend (increasing/decreasing)
        4. The volatility of demand
        5. The category of the product
        6. Historical order patterns
        
        Please provide:
        1. Top products most likely to be ordered in the next forecast period
        2. Recommended order quantities for each product
        3. Optimal ordering schedule (which days to place orders)
        4. Seasonal or trend insights
        5. Risk assessment (products that might be over/under-stocked)
        6. Cost optimization suggestions
        
        Format your response as a JSON object:
        {{
          "recommended_products": [
            {{
              "product_name": "Actual Product Name",
              "product_id": "ID-X",
              "recommended_quantity": 5,
              "confidence": 85,
              "optimal_order_date": "YYYY-MM-DD",
              "reasoning": "explanation"
            }}
          ],
          "ordering_schedule": [
            {{
              "date": "YYYY-MM-DD",
              "products": ["Product A", "Product B"],
              "total_items": 15
            }}
          ],
          "insights": {{
            "seasonal_trends": "description",
            "risk_assessment": "description",
            "cost_optimization": "suggestions"
          }}
        }}
        """
        
        logger.info("Sending prompt to Bedrock...")
        # Call Bedrock matching notebook approach
        if bedrock_model_id.startswith('anthropic.'):
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.2,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
        else:
            body = json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 2000,
                    "temperature": 0.2
                }
            })
        
        response = bedrock_client.invoke_model(
            modelId=bedrock_model_id,
            contentType='application/json',
            accept='application/json',
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        logger.info("Received response from Bedrock")
        
        # Extract the response based on model type (matching notebook)
        if bedrock_model_id.startswith('anthropic.'):
            response_text = response_body.get('content', [{}])[0].get('text', '')
        else:
            response_text = response_body.get('results', [{}])[0].get('outputText', '')
        
        logger.info(f"Raw Bedrock response: {response_text}")
        
        # Extract JSON from the response (matching notebook approach)
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                recommendations = json.loads(json_str)
                logger.info("Successfully parsed JSON from Bedrock response")
                return recommendations
            else:
                raise ValueError("No JSON found in response")
        except Exception as json_error:
            logger.error(f"Error parsing JSON from Bedrock response: {str(json_error)}")
            logger.info(f"Raw response: {response_text}")
            
            # Fallback recommendations
            return generate_fallback_recommendations(product_predictions)
    
    except Exception as e:
        logger.error(f"Error calling Bedrock: {str(e)}")
        return generate_fallback_recommendations(product_predictions)

def generate_fallback_recommendations(product_predictions):
    """Generate fallback recommendations when Bedrock fails, matching notebook's mock data approach"""
    try:
        logger.info("Generating fallback recommendations using notebook's approach")
        recommended_products = []
        
        # Sort products by predicted demand and historical patterns (matching notebook logic)
        sorted_products = []
        for pred in product_predictions:
            predictions = pred['predictions']
            if predictions:
                # Calculate average predicted quantity (matching notebook calculations)
                p50_values = [day_pred.get('p50', day_pred.get('mean', 0)) for day_pred in predictions.values()]
                avg_predicted = float(np.mean(p50_values)) if p50_values else 0
                
                # Calculate trend
                trend_score = 0
                if len(p50_values) > 1:
                    trend_score = p50_values[-1] - p50_values[0]
                
                # Combine predicted demand with historical order frequency
                historical_weight = pred['order_history']['order_count']
                combined_score = avg_predicted * 0.7 + (historical_weight / 100) * 0.3 + trend_score * 0.1
                
                sorted_products.append({
                    'prediction': pred,
                    'avg_predicted': avg_predicted,
                    'combined_score': combined_score,
                    'trend_score': trend_score
                })
        
        # Sort by combined score and take top products
        sorted_products = sorted(sorted_products, key=lambda x: x['combined_score'], reverse=True)[:5]
        
        # Generate recommendations matching notebook format
        for i, item in enumerate(sorted_products):
            pred = item['prediction']
            avg_predicted = item['avg_predicted']
            
            # Calculate confidence based on prediction consistency (matching notebook approach)
            predictions = pred['predictions']
            p50_values = [day_pred.get('p50', day_pred.get('mean', 0)) for day_pred in predictions.values()]
            p10_values = [day_pred.get('p10', 0) for day_pred in predictions.values()]
            p90_values = [day_pred.get('p90', 0) for day_pred in predictions.values()]
            
            # Calculate confidence interval width
            if p10_values and p90_values:
                confidence_width = np.mean(np.array(p90_values) - np.array(p10_values))
                confidence = max(50, min(95, 100 - (confidence_width / avg_predicted * 50))) if avg_predicted > 0 else 60
            else:
                confidence = 60
            
            # Determine optimal order date based on trend
            days_ahead = 1 if item['trend_score'] >= 0 else 2  # Order sooner if demand is increasing
            optimal_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
            
            # Generate reasoning matching notebook's analytical approach
            trend_desc = "increasing" if item['trend_score'] > 0 else "stable" if item['trend_score'] == 0 else "decreasing"
            reasoning = f"Predicted avg demand: {avg_predicted:.1f}, trend: {trend_desc}, historical orders: {pred['order_history']['order_count']}"
            
            recommended_products.append({
                'product_name': pred['product_name'],
                'product_id': pred['product_id'],
                'recommended_quantity': max(1, int(avg_predicted * 1.1)),  # Add 10% buffer
                'confidence': int(confidence),
                'optimal_order_date': optimal_date,
                'reasoning': reasoning
            })
        
        # Generate ordering schedule (matching notebook approach)
        ordering_schedule = []
        schedule_dates = {}
        
        for product in recommended_products:
            order_date = product['optimal_order_date']
            if order_date not in schedule_dates:
                schedule_dates[order_date] = {
                    'date': order_date,
                    'products': [],
                    'total_items': 0
                }
            schedule_dates[order_date]['products'].append(product['product_name'])
            schedule_dates[order_date]['total_items'] += product['recommended_quantity']
        
        ordering_schedule = list(schedule_dates.values())
        
        # Generate insights matching notebook's analytical approach
        total_products = len(product_predictions)
        high_confidence_products = len([p for p in recommended_products if p['confidence'] > 80])
        avg_confidence = np.mean([p['confidence'] for p in recommended_products]) if recommended_products else 0
        
        insights = {
            'seasonal_trends': f'Analysis based on {total_products} products with varying demand patterns. Consider seasonal factors for procurement planning.',
            'risk_assessment': f'{high_confidence_products}/{len(recommended_products)} recommendations have high confidence (>80%). Average confidence: {avg_confidence:.1f}%',
            'cost_optimization': 'Consider consolidating orders by date to reduce procurement costs. Monitor high-volatility products for inventory optimization.'
        }
        
        return {
            'recommended_products': recommended_products,
            'ordering_schedule': ordering_schedule,
            'insights': insights
        }
        
    except Exception as e:
        logger.error(f"Error generating fallback recommendations: {str(e)}")
        return {
            'recommended_products': [],
            'ordering_schedule': [],
            'insights': {
                'seasonal_trends': 'Unable to analyze trends due to processing error',
                'risk_assessment': 'Risk assessment unavailable',
                'cost_optimization': 'Cost optimization suggestions unavailable'
            }
        }

def lambda_handler(event, context):
    """Enhanced Lambda function handler for product-level predictions"""
    try:
        # Extract customer and facility IDs
        customer_id = event.get('customerId')
        facility_id = event.get('facilityId')
        prediction_id = event.get('predictionId', str(uuid.uuid4()))
        
        if not customer_id or not facility_id:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'message': 'Missing required parameters: customerId and facilityId'
                })
            }
        
        # Get product lookup data
        product_lookup_df, customer_product_lookup_df = get_product_lookup_data()
        
        if customer_product_lookup_df.empty:
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'message': 'No product data found. Please ensure data has been processed.'
                })
            }
        
        # Query product-level forecasts from SageMaker
        product_predictions = query_sagemaker_for_predictions(
            customer_id, facility_id, product_lookup_df, customer_product_lookup_df
        )
        
        if not product_predictions:
            logger.warning(f"No products found for customer {customer_id} at facility {facility_id}")
            return {
            'statusCode': 404,
            'body': json.dumps({
                'message': f'No products found for customer {customer_id} at facility {facility_id}'
            })
            }
        
        logger.info(f"Found {len(product_predictions)} products to analyze for customer {customer_id} at facility {facility_id}")
        
        # Get enhanced recommendations from Bedrock
        logger.info(f"Calling Bedrock for recommendations with {len(product_predictions)} products")
        recommendations = call_bedrock_for_product_recommendations(
            product_predictions, customer_id, facility_id
        )
        logger.info(f"Received recommendations with {len(recommendations.get('recommended_products', []))} recommended products")
        
        # Prepare the response matching notebook's JSON structure
        result = {
            'id': prediction_id,
            'timestamp': datetime.now().isoformat(),
            'customerId': customer_id,
            'facilityId': facility_id,
            'productPredictions': product_predictions,
            'recommendations': recommendations,
            'summary': {
                'total_products_analyzed': len(product_predictions),
                'recommended_products_count': len(recommendations.get('recommended_products', [])),
                'next_suggested_order_date': recommendations.get('ordering_schedule', [{}])[0].get('date') if recommendations.get('ordering_schedule') else None,
                'avg_confidence': np.mean([p.get('confidence', 0) for p in recommendations.get('recommended_products', [])]) if recommendations.get('recommended_products') else 0,
                'high_confidence_products': len([p for p in recommendations.get('recommended_products', []) if p.get('confidence', 0) > 80])
            }
        }
        
        return {
            'statusCode': 200,
            'body': json.dumps(result, default=str)  # default=str to handle datetime objects
        }
        
    except Exception as e:
        logger.error(f"Error generating product predictions: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error generating product predictions: {str(e)}'
            })
        }
