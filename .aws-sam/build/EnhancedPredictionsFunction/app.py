import json
import boto3
import os
import logging
from datetime import datetime, timedelta
import uuid
import pandas as pd

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

def query_sagemaker_for_predictions(customer_id, facility_id, product_lookup_df, customer_product_lookup_df):
    """Query SageMaker Canvas for product-level predictions"""
    try:
        if not sagemaker_endpoint_name:
            logger.warning("No SageMaker endpoint available, using mock data")
            return generate_mock_product_predictions(customer_id, facility_id, customer_product_lookup_df)

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

        # Prepare the input data for SageMaker
        sagemaker_input_df = customer_products[['CustomerID', 'FacilityID', 'ProductID', 'ProductCategory', 'ProductDescription']].copy()
        sagemaker_input_df['target_value'] = 0 # Add the required target column with a placeholder value
        sagemaker_input_csv = sagemaker_input_df.to_csv(index=False)

        logger.info(f"Invoking SageMaker endpoint: {sagemaker_endpoint_name}")
        response = sagemaker_runtime_client.invoke_endpoint(
            EndpointName=sagemaker_endpoint_name,
            ContentType='text/csv',
            Body=sagemaker_input_csv
        )

        # Process the SageMaker response
        result_csv = response['Body'].read().decode('utf-8')
        predictions_df = pd.read_csv(pd.io.common.StringIO(result_csv))
        
        # Merge predictions back with original data
        merged_df = pd.merge(customer_products, predictions_df, on='ProductID', how='left')

        product_predictions = []
        for _, pred_row in merged_df.iterrows():
            product_id = pred_row['ProductID']
            
            # This part needs to be adapted based on the actual output format of your Canvas model
            predicted_value = pred_row.get('prediction', 0) # IMPORTANT: Check this column name

            predictions = {}
            for i in range(7):
                date_str = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
                predictions[date_str] = {
                    'p10': predicted_value * 0.5, # Mocking quantiles
                    'p50': predicted_value,
                    'p90': predicted_value * 1.5,
                    'mean': predicted_value
                }

            product_predictions.append({
                'product_id': product_id,
                'product_name': pred_row['ProductName'],
                'category_name': pred_row['CategoryName'],
                'vendor_name': pred_row['vendorName'],
                'predictions': predictions,
                'order_history': {
                    'order_count': pred_row['OrderCount'],
                    'first_order': pred_row['FirstOrderDate'],
                    'last_order': pred_row['LastOrderDate']
                }
            })

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
    """Call Amazon Bedrock to generate product recommendations and insights"""
    try:
        logger.info(f"Calling Bedrock for customer {customer_id}, facility {facility_id}")
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Prepare product data for the prompt
        product_summary = []
        for pred in product_predictions[:10]:  # Limit to top 10 for prompt size
            product_summary.append({
                'product_name': pred['product_name'],
                'category': pred['category_name'],
                'vendor': pred['vendor_name'],
                'historical_orders': pred['order_history']['order_count'],
                'predicted_quantities': pred['predictions']
            })
        
        logger.info(f"Prepared {len(product_summary)} products for Bedrock prompt")
        
        prompt = f"""
        Based on the following product-level demand forecasts for Customer {customer_id} at Facility {facility_id}:
        
        Current date: {current_date}
        Product predictions: {json.dumps(product_summary, indent=2)}
        
        Please provide:
        1. Top 5-10 products most likely to be ordered in the next 7 days
        2. Recommended order quantities for each product
        3. Optimal ordering schedule (which days to place orders)
        4. Any seasonal or trend insights
        5. Risk assessment (products that might be over/under-stocked)
        
        Format your response as a JSON object:
        {{
          "recommended_products": [
            {{
              "product_name": "Product Name",
              "category": "Category",
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
        # Call Bedrock
        if bedrock_model_id.startswith('anthropic.'):
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.2,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
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
        
        # Extract the response based on model type
        if bedrock_model_id.startswith('anthropic.'):
            response_text = response_body.get('content', [{}])[0].get('text', '')
        else:
            response_text = response_body.get('results', [{}])[0].get('outputText', '')
        
        logger.info(f"Raw Bedrock response: {response_text}")
        
        # Extract JSON from the response
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                recommendations = json.loads(json_str)
                logger.info("Successfully parsed JSON from Bedrock response")
            else:
                raise ValueError("No JSON found in response")
        except Exception as json_error:
            logger.error(f"Error parsing JSON from Bedrock response: {str(json_error)}")
            logger.info(f"Raw response: {response_text}")
            
            # Fallback recommendations
            recommendations = generate_fallback_recommendations(product_predictions)
        
        return recommendations
    
    except Exception as e:
        logger.error(f"Error calling Bedrock: {str(e)}")
        return generate_fallback_recommendations(product_predictions)

def generate_fallback_recommendations(product_predictions):
    """Generate fallback recommendations when Bedrock fails"""
    try:
        recommended_products = []
        
        # Sort products by historical order count and recent predictions
        for pred in sorted(product_predictions, key=lambda x: x['order_history']['order_count'], reverse=True)[:5]:
            # Get average predicted quantity for next few days
            predictions = pred['predictions']
            if predictions:
                avg_quantity = sum([day_pred.get('mean', 0) for day_pred in predictions.values()]) / len(predictions)
            else:
                avg_quantity = 1
            
            recommended_products.append({
                'product_name': pred['product_name'],
                'category': pred['category_name'],
                'recommended_quantity': max(1, int(avg_quantity)),
                'confidence': 60,
                'optimal_order_date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                'reasoning': f"Based on historical order frequency of {pred['order_history']['order_count']} orders"
            })
        
        return {
            'recommended_products': recommended_products,
            'ordering_schedule': [
                {
                    'date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                    'products': [p['product_name'] for p in recommended_products[:3]],
                    'total_items': sum([p['recommended_quantity'] for p in recommended_products[:3]])
                }
            ],
            'insights': {
                'seasonal_trends': 'Analysis based on historical order patterns',
                'risk_assessment': 'Recommendations based on past ordering frequency',
                'cost_optimization': 'Consider bulk ordering for frequently ordered items'
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating fallback recommendations: {str(e)}")
        return {
            'recommended_products': [],
            'ordering_schedule': [],
            'insights': {}
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
        
        # Prepare the response
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
                'next_suggested_order_date': recommendations.get('ordering_schedule', [{}])[0].get('date') if recommendations.get('ordering_schedule') else None
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
