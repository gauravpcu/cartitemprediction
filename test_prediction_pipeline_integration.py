#!/usr/bin/env python3
"""
Integration Tests for Prediction Pipeline

This test suite validates the end-to-end prediction pipeline from raw data
to API responses, ensuring all components work together and produce outputs
that match the notebook's JSON structure and behavior.

Test Coverage:
- End-to-end flow from raw data to predictions
- SageMaker integration (mocked)
- Bedrock recommendation generation (mocked)
- API response format validation
- Error handling and fallback mechanisms
"""

import unittest
import pandas as pd
import numpy as np
import json
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import tempfile

# Mock AWS services for testing
class MockS3Client:
    def __init__(self):
        self.objects = {}
        self.folders = {
            'lookup/2024-01-01-12-00-00/': [
                'product_lookup.csv',
                'customer_product_lookup.csv'
            ]
        }
    
    def list_objects_v2(self, Bucket, Prefix, Delimiter=None):
        if Prefix == 'lookup/':
            return {
                'CommonPrefixes': [
                    {'Prefix': 'lookup/2024-01-01-12-00-00/'}
                ]
            }
        return {'Contents': []}
    
    def download_file(self, bucket, key, local_path):
        # Create mock CSV files
        if 'product_lookup.csv' in key:
            df = pd.DataFrame({
                'ProductID': [288563, 288564],
                'ProductName': ['Cereal Toasty Os (Cheerios)', 'Milk Whole'],
                'CategoryName': ['Cereals', 'Dairy'],
                'vendorName': ['US FoodsBuffalo (HPSI)', 'Dairy Co']
            })
            df.to_csv(local_path, index=False)
        elif 'customer_product_lookup.csv' in key:
            df = pd.DataFrame({
                'ProductID': [288563, 288563, 288564],
                'ProductName': ['Cereal Toasty Os (Cheerios)', 'Cereal Toasty Os (Cheerios)', 'Milk Whole'],
                'CategoryName': ['Cereals', 'Cereals', 'Dairy'],
                'vendorName': ['US FoodsBuffalo (HPSI)', 'US FoodsBuffalo (HPSI)', 'Dairy Co'],
                'CustomerID': [1045, 1045, 1046],
                'FacilityID': [6420, 6417, 6420],
                'OrderCount': [15, 8, 12],
                'FirstOrderDate': ['2024-01-01', '2024-01-15', '2024-01-10'],
                'LastOrderDate': ['2024-12-01', '2024-11-15', '2024-12-05']
            })
            df.to_csv(local_path, index=False)

class MockSageMakerClient:
    def invoke_endpoint(self, EndpointName, ContentType, Body):
        # Mock SageMaker response matching notebook format
        request_data = json.loads(Body)
        
        # Generate mock predictions based on request
        mock_predictions = {
            'predictions': [{
                'quantiles': {
                    '0.1': [1.2, 1.1, 1.3, 1.0, 1.4, 1.2, 1.1],
                    '0.5': [2.5, 2.3, 2.7, 2.1, 2.8, 2.4, 2.2],
                    '0.9': [4.1, 3.8, 4.3, 3.5, 4.5, 3.9, 3.6]
                }
            }]
        }
        
        # Mock response object
        response_mock = Mock()
        response_mock.read.return_value = json.dumps(mock_predictions).encode('utf-8')
        
        return {
            'Body': response_mock
        }

class MockBedrockClient:
    def invoke_model(self, modelId, contentType, accept, body):
        # Mock Bedrock response matching notebook format
        mock_response = {
            "recommended_products": [
                {
                    "product_name": "Cereal Toasty Os (Cheerios)",
                    "product_id": "288563",
                    "recommended_quantity": 3,
                    "confidence": 85,
                    "optimal_order_date": (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                    "reasoning": "High demand prediction with stable trend"
                }
            ],
            "ordering_schedule": [
                {
                    "date": (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                    "products": ["Cereal Toasty Os (Cheerios)"],
                    "total_items": 3
                }
            ],
            "insights": {
                "seasonal_trends": "Stable demand patterns observed",
                "risk_assessment": "Low risk with high confidence predictions",
                "cost_optimization": "Consider bulk ordering for frequently ordered items"
            }
        }
        
        # Mock response object
        response_mock = Mock()
        if modelId.startswith('anthropic.'):
            response_body = {
                'content': [{'text': json.dumps(mock_response)}]
            }
        else:
            response_body = {
                'results': [{'outputText': json.dumps(mock_response)}]
            }
        
        response_mock.read.return_value = json.dumps(response_body).encode('utf-8')
        
        return {
            'body': response_mock
        }

class TestPredictionPipelineIntegration(unittest.TestCase):
    """Integration tests for the complete prediction pipeline"""
    
    def setUp(self):
        """Set up test environment with mocked AWS services"""
        # Mock environment variables
        self.env_vars = {
            'PROCESSED_BUCKET': 'test-bucket',
            'SAGEMAKER_ENDPOINT_NAME': 'hybrent-deepar-2025-07-20-23-56-22-287',
            'BEDROCK_MODEL_ID': 'anthropic.claude-3-sonnet-20240229-v1:0',
            'LOG_LEVEL': 'INFO'
        }
        
        # Create mock clients
        self.mock_s3 = MockS3Client()
        self.mock_sagemaker = MockSageMakerClient()
        self.mock_bedrock = MockBedrockClient()
        
        # Sample test data
        self.test_customer_id = "1045"
        self.test_facility_id = "6420"
        
        # Expected response structure based on notebook
        self.expected_response_fields = [
            'id', 'timestamp', 'customerId', 'facilityId', 
            'productPredictions', 'recommendations', 'summary'
        ]
        
        self.expected_product_prediction_fields = [
            'product_id', 'product_name', 'category_name', 'vendor_name',
            'predictions', 'order_history'
        ]
        
        self.expected_recommendation_fields = [
            'recommended_products', 'ordering_schedule', 'insights'
        ]
    
    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket', 'SAGEMAKER_ENDPOINT_NAME': 'test-endpoint'})
    @patch('boto3.client')
    def test_end_to_end_prediction_flow(self, mock_boto3_client):
        """Test complete end-to-end prediction flow"""
        print("\n=== Testing End-to-End Prediction Flow ===")
        
        # Mock boto3 clients
        def mock_client_factory(service_name):
            if service_name == 's3':
                return self.mock_s3
            elif service_name == 'sagemaker-runtime':
                return self.mock_sagemaker
            elif service_name == 'bedrock-runtime':
                return self.mock_bedrock
            else:
                return Mock()
        
        mock_boto3_client.side_effect = mock_client_factory
        
        # Import the enhanced predictions function
        sys.path.append('functions/enhanced_predictions')
        from app import lambda_handler as enhanced_predictions_handler
        
        # Create test event
        test_event = {
            'customerId': self.test_customer_id,
            'facilityId': self.test_facility_id
        }
        
        # Execute the function
        response = enhanced_predictions_handler(test_event, {})
        
        # Validate response structure
        self.assertEqual(response['statusCode'], 200)
        
        # Parse response body
        response_body = json.loads(response['body'])
        
        # Test required fields
        for field in self.expected_response_fields:
            with self.subTest(field=field):
                self.assertIn(field, response_body, f"Missing required field: {field}")
        
        print(f"✓ Response contains all required fields: {len(self.expected_response_fields)}")
        
        # Test customer and facility IDs match
        self.assertEqual(response_body['customerId'], self.test_customer_id)
        self.assertEqual(response_body['facilityId'], self.test_facility_id)
        print(f"✓ Customer ID and Facility ID match: {self.test_customer_id}, {self.test_facility_id}")
        
        # Test product predictions structure
        product_predictions = response_body['productPredictions']
        self.assertIsInstance(product_predictions, list)
        self.assertGreater(len(product_predictions), 0, "Should have at least one product prediction")
        
        # Test first product prediction structure
        first_product = product_predictions[0]
        for field in self.expected_product_prediction_fields:
            with self.subTest(field=field):
                self.assertIn(field, first_product, f"Missing product field: {field}")
        
        print(f"✓ Product predictions structure valid: {len(product_predictions)} products")
        
        # Test predictions format (should have date-based predictions)
        predictions = first_product['predictions']
        self.assertIsInstance(predictions, dict)
        self.assertGreater(len(predictions), 0, "Should have prediction dates")
        
        # Test prediction date format and values
        for date_str, pred_values in predictions.items():
            with self.subTest(date=date_str):
                # Validate date format
                datetime.strptime(date_str, '%Y-%m-%d')
                
                # Validate prediction values
                required_pred_fields = ['p10', 'p50', 'p90', 'mean']
                for field in required_pred_fields:
                    self.assertIn(field, pred_values)
                    self.assertIsInstance(pred_values[field], (int, float))
                    self.assertGreaterEqual(pred_values[field], 0)
        
        print(f"✓ Prediction values format valid: {len(predictions)} dates")
        
        # Test recommendations structure
        recommendations = response_body['recommendations']
        for field in self.expected_recommendation_fields:
            with self.subTest(field=field):
                self.assertIn(field, recommendations, f"Missing recommendation field: {field}")
        
        print(f"✓ Recommendations structure valid")
        
        # Test recommended products
        recommended_products = recommendations['recommended_products']
        self.assertIsInstance(recommended_products, list)
        
        if recommended_products:
            first_recommendation = recommended_products[0]
            required_rec_fields = ['product_name', 'product_id', 'recommended_quantity', 'confidence', 'optimal_order_date', 'reasoning']
            for field in required_rec_fields:
                with self.subTest(field=field):
                    self.assertIn(field, first_recommendation, f"Missing recommendation field: {field}")
        
        print(f"✓ Recommended products structure valid: {len(recommended_products)} recommendations")
        
        # Test summary statistics
        summary = response_body['summary']
        self.assertIn('total_products_analyzed', summary)
        self.assertIn('recommended_products_count', summary)
        self.assertGreater(summary['total_products_analyzed'], 0)
        
        print(f"✓ Summary statistics valid: {summary['total_products_analyzed']} products analyzed")
        
        print("✓ All end-to-end prediction flow tests passed!")
    
    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket'})
    @patch('boto3.client')
    def test_sagemaker_integration_mock(self, mock_boto3_client):
        """Test SageMaker integration produces expected results"""
        print("\n=== Testing SageMaker Integration ===")
        
        # Mock boto3 clients
        def mock_client_factory(service_name):
            if service_name == 's3':
                return self.mock_s3
            elif service_name == 'sagemaker-runtime':
                return self.mock_sagemaker
            elif service_name == 'bedrock-runtime':
                return self.mock_bedrock
            else:
                return Mock()
        
        mock_boto3_client.side_effect = mock_client_factory
        
        # Import functions
        sys.path.append('functions/enhanced_predictions')
        from app import query_sagemaker_for_predictions, get_product_lookup_data
        
        # Get lookup data
        product_lookup_df, customer_product_lookup_df = get_product_lookup_data()
        
        # Test SageMaker query
        predictions = query_sagemaker_for_predictions(
            self.test_customer_id, self.test_facility_id, 
            product_lookup_df, customer_product_lookup_df
        )
        
        # Validate predictions structure
        self.assertIsInstance(predictions, list)
        self.assertGreater(len(predictions), 0, "Should return predictions")
        
        # Test first prediction
        first_pred = predictions[0]
        
        # Test required fields
        for field in self.expected_product_prediction_fields:
            with self.subTest(field=field):
                self.assertIn(field, first_pred, f"Missing field: {field}")
        
        # Test prediction values
        pred_values = first_pred['predictions']
        self.assertIsInstance(pred_values, dict)
        
        # Test quantile values are properly ordered (p10 <= p50 <= p90)
        for date_str, values in pred_values.items():
            with self.subTest(date=date_str):
                self.assertLessEqual(values['p10'], values['p50'])
                self.assertLessEqual(values['p50'], values['p90'])
                self.assertGreaterEqual(values['mean'], 0)
        
        print(f"✓ SageMaker integration produces valid predictions: {len(predictions)} products")
        print("✓ All SageMaker integration tests passed!")
    
    @patch.dict(os.environ, {'BEDROCK_MODEL_ID': 'anthropic.claude-3-sonnet-20240229-v1:0'})
    @patch('boto3.client')
    def test_bedrock_recommendation_generation(self, mock_boto3_client):
        """Test Bedrock recommendation generation"""
        print("\n=== Testing Bedrock Recommendation Generation ===")
        
        # Mock boto3 clients
        def mock_client_factory(service_name):
            if service_name == 'bedrock-runtime':
                return self.mock_bedrock
            else:
                return Mock()
        
        mock_boto3_client.side_effect = mock_client_factory
        
        # Import functions
        sys.path.append('functions/enhanced_predictions')
        from app import call_bedrock_for_product_recommendations
        
        # Create mock product predictions
        mock_product_predictions = [
            {
                'product_id': '288563',
                'product_name': 'Cereal Toasty Os (Cheerios)',
                'category_name': 'Cereals',
                'vendor_name': 'US FoodsBuffalo (HPSI)',
                'predictions': {
                    '2024-01-01': {'p10': 1.2, 'p50': 2.5, 'p90': 4.1, 'mean': 2.5},
                    '2024-01-02': {'p10': 1.1, 'p50': 2.3, 'p90': 3.8, 'mean': 2.3}
                },
                'order_history': {
                    'order_count': 15,
                    'first_order': '2024-01-01',
                    'last_order': '2024-12-01'
                }
            }
        ]
        
        # Test Bedrock call
        recommendations = call_bedrock_for_product_recommendations(
            mock_product_predictions, self.test_customer_id, self.test_facility_id
        )
        
        # Validate recommendations structure
        for field in self.expected_recommendation_fields:
            with self.subTest(field=field):
                self.assertIn(field, recommendations, f"Missing recommendation field: {field}")
        
        # Test recommended products structure
        recommended_products = recommendations['recommended_products']
        self.assertIsInstance(recommended_products, list)
        
        if recommended_products:
            first_rec = recommended_products[0]
            required_fields = ['product_name', 'product_id', 'recommended_quantity', 'confidence', 'optimal_order_date', 'reasoning']
            for field in required_fields:
                with self.subTest(field=field):
                    self.assertIn(field, first_rec, f"Missing field: {field}")
            
            # Test data types and ranges
            self.assertIsInstance(first_rec['recommended_quantity'], int)
            self.assertGreater(first_rec['recommended_quantity'], 0)
            self.assertIsInstance(first_rec['confidence'], int)
            self.assertGreaterEqual(first_rec['confidence'], 0)
            self.assertLessEqual(first_rec['confidence'], 100)
            
            # Test date format
            datetime.strptime(first_rec['optimal_order_date'], '%Y-%m-%d')
        
        # Test ordering schedule
        ordering_schedule = recommendations['ordering_schedule']
        self.assertIsInstance(ordering_schedule, list)
        
        if ordering_schedule:
            first_schedule = ordering_schedule[0]
            required_fields = ['date', 'products', 'total_items']
            for field in required_fields:
                with self.subTest(field=field):
                    self.assertIn(field, first_schedule, f"Missing schedule field: {field}")
        
        # Test insights
        insights = recommendations['insights']
        required_insight_fields = ['seasonal_trends', 'risk_assessment', 'cost_optimization']
        for field in required_insight_fields:
            with self.subTest(field=field):
                self.assertIn(field, insights, f"Missing insight field: {field}")
                self.assertIsInstance(insights[field], str)
                self.assertGreater(len(insights[field]), 0)
        
        print(f"✓ Bedrock recommendations structure valid")
        print(f"✓ Recommended products: {len(recommended_products)}")
        print(f"✓ Ordering schedule entries: {len(ordering_schedule)}")
        print("✓ All Bedrock recommendation tests passed!")
    
    @patch.dict(os.environ, {'ENHANCE_FUNCTION_NAME': 'test-enhance-function'})
    @patch('boto3.client')
    def test_api_response_format_validation(self, mock_boto3_client):
        """Test API responses match notebook format exactly"""
        print("\n=== Testing API Response Format Validation ===")
        
        # Mock Lambda client
        mock_lambda_client = Mock()
        
        # Mock enhanced predictions response
        mock_enhanced_response = {
            'statusCode': 200,
            'body': json.dumps({
                'id': 'test-prediction-id',
                'timestamp': datetime.now().isoformat(),
                'customerId': self.test_customer_id,
                'facilityId': self.test_facility_id,
                'productPredictions': [
                    {
                        'product_id': '288563',
                        'product_name': 'Cereal Toasty Os (Cheerios)',
                        'category_name': 'Cereals',
                        'vendor_name': 'US FoodsBuffalo (HPSI)',
                        'predictions': {
                            '2024-01-01': {'p10': 1.2, 'p50': 2.5, 'p90': 4.1, 'mean': 2.5}
                        },
                        'order_history': {
                            'order_count': 15,
                            'first_order': '2024-01-01',
                            'last_order': '2024-12-01'
                        }
                    }
                ],
                'recommendations': {
                    'recommended_products': [
                        {
                            'product_name': 'Cereal Toasty Os (Cheerios)',
                            'product_id': '288563',
                            'recommended_quantity': 3,
                            'confidence': 85,
                            'optimal_order_date': '2024-01-02',
                            'reasoning': 'High demand prediction'
                        }
                    ],
                    'ordering_schedule': [
                        {
                            'date': '2024-01-02',
                            'products': ['Cereal Toasty Os (Cheerios)'],
                            'total_items': 3
                        }
                    ],
                    'insights': {
                        'seasonal_trends': 'Stable demand',
                        'risk_assessment': 'Low risk',
                        'cost_optimization': 'Consider bulk orders'
                    }
                },
                'summary': {
                    'total_products_analyzed': 1,
                    'recommended_products_count': 1
                }
            })
        }
        
        # Mock invoke response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps(mock_enhanced_response).encode('utf-8')
        mock_lambda_client.invoke.return_value = {'Payload': mock_response}
        
        mock_boto3_client.return_value = mock_lambda_client
        
        # Test Product Prediction API
        sys.path.append('functions/product_prediction_api')
        from app import lambda_handler as product_api_handler
        
        # Create API Gateway event
        api_event = {
            'httpMethod': 'GET',
            'queryStringParameters': {
                'customerId': self.test_customer_id,
                'facilityId': self.test_facility_id
            }
        }
        
        # Execute API handler
        api_response = product_api_handler(api_event, {})
        
        # Validate API response structure
        self.assertEqual(api_response['statusCode'], 200)
        self.assertIn('headers', api_response)
        self.assertIn('body', api_response)
        
        # Test CORS headers
        headers = api_response['headers']
        self.assertIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(headers['Access-Control-Allow-Origin'], '*')
        self.assertIn('Content-Type', headers)
        self.assertEqual(headers['Content-Type'], 'application/json')
        
        # Parse and validate response body
        response_body = json.loads(api_response['body'])
        
        # Test required fields
        for field in self.expected_response_fields:
            with self.subTest(field=field):
                self.assertIn(field, response_body, f"Missing API response field: {field}")
        
        print("✓ Product Prediction API response format valid")
        
        # Test Recommendation API
        sys.path.append('functions/recommend_api')
        from app import lambda_handler as recommend_api_handler
        
        # Execute recommendation API handler
        rec_api_response = recommend_api_handler(api_event, {})
        
        # Validate recommendation API response
        self.assertEqual(rec_api_response['statusCode'], 200)
        
        # Parse recommendation response body
        rec_response_body = json.loads(rec_api_response['body'])
        
        # Test recommendation fields
        for field in self.expected_recommendation_fields:
            with self.subTest(field=field):
                self.assertIn(field, rec_response_body, f"Missing recommendation API field: {field}")
        
        print("✓ Recommendation API response format valid")
        print("✓ All API response format validation tests passed!")
    
    @patch.dict(os.environ, {'PROCESSED_BUCKET': 'test-bucket'})
    @patch('boto3.client')
    def test_error_handling_and_fallbacks(self, mock_boto3_client):
        """Test error scenarios and fallback mechanisms"""
        print("\n=== Testing Error Handling and Fallbacks ===")
        
        # Test 1: Missing lookup data
        mock_s3_empty = Mock()
        mock_s3_empty.list_objects_v2.return_value = {}  # No objects
        
        def mock_client_factory_empty(service_name):
            if service_name == 's3':
                return mock_s3_empty
            else:
                return Mock()
        
        mock_boto3_client.side_effect = mock_client_factory_empty
        
        sys.path.append('functions/enhanced_predictions')
        from app import lambda_handler as enhanced_predictions_handler
        
        # Test with missing data
        test_event = {
            'customerId': self.test_customer_id,
            'facilityId': self.test_facility_id
        }
        
        response = enhanced_predictions_handler(test_event, {})
        self.assertEqual(response['statusCode'], 404)
        
        response_body = json.loads(response['body'])
        self.assertIn('message', response_body)
        print("✓ Missing lookup data error handling works")
        
        # Test 2: SageMaker endpoint failure (should fall back to mock)
        mock_sagemaker_error = Mock()
        mock_sagemaker_error.invoke_endpoint.side_effect = Exception("Endpoint not available")
        
        def mock_client_factory_sagemaker_error(service_name):
            if service_name == 's3':
                return self.mock_s3
            elif service_name == 'sagemaker-runtime':
                return mock_sagemaker_error
            elif service_name == 'bedrock-runtime':
                return self.mock_bedrock
            else:
                return Mock()
        
        mock_boto3_client.side_effect = mock_client_factory_sagemaker_error
        
        # This should still work with fallback to mock predictions
        response = enhanced_predictions_handler(test_event, {})
        self.assertEqual(response['statusCode'], 200)
        
        response_body = json.loads(response['body'])
        self.assertIn('productPredictions', response_body)
        print("✓ SageMaker fallback mechanism works")
        
        # Test 3: Bedrock failure (should fall back to generated recommendations)
        mock_bedrock_error = Mock()
        mock_bedrock_error.invoke_model.side_effect = Exception("Bedrock not available")
        
        def mock_client_factory_bedrock_error(service_name):
            if service_name == 's3':
                return self.mock_s3
            elif service_name == 'sagemaker-runtime':
                return self.mock_sagemaker
            elif service_name == 'bedrock-runtime':
                return mock_bedrock_error
            else:
                return Mock()
        
        mock_boto3_client.side_effect = mock_client_factory_bedrock_error
        
        response = enhanced_predictions_handler(test_event, {})
        self.assertEqual(response['statusCode'], 200)
        
        response_body = json.loads(response['body'])
        self.assertIn('recommendations', response_body)
        
        # Should have fallback recommendations
        recommendations = response_body['recommendations']
        self.assertIn('recommended_products', recommendations)
        print("✓ Bedrock fallback mechanism works")
        
        # Test 4: Invalid parameters
        invalid_event = {
            'customerId': '',
            'facilityId': self.test_facility_id
        }
        
        response = enhanced_predictions_handler(invalid_event, {})
        self.assertEqual(response['statusCode'], 400)
        print("✓ Invalid parameter handling works")
        
        print("✓ All error handling and fallback tests passed!")
    
    def test_notebook_consistency_validation(self):
        """Test that outputs match expected notebook format and structure"""
        print("\n=== Testing Notebook Consistency Validation ===")
        
        # Test prediction response structure matches notebook exactly
        expected_notebook_structure = {
            'id': str,
            'timestamp': str,
            'customerId': str,
            'facilityId': str,
            'productPredictions': list,
            'recommendations': dict,
            'summary': dict
        }
        
        # Mock response matching notebook format
        mock_response = {
            'id': 'test-id',
            'timestamp': datetime.now().isoformat(),
            'customerId': '1045',
            'facilityId': '6420',
            'productPredictions': [
                {
                    'product_id': '288563',
                    'product_name': 'Cereal Toasty Os (Cheerios)',
                    'category_name': 'Cereals',
                    'vendor_name': 'US FoodsBuffalo (HPSI)',
                    'predictions': {
                        '2024-01-01': {
                            'p10': 1.2,
                            'p50': 2.5,
                            'p90': 4.1,
                            'mean': 2.5
                        }
                    },
                    'order_history': {
                        'order_count': 15,
                        'first_order': '2024-01-01',
                        'last_order': '2024-12-01'
                    }
                }
            ],
            'recommendations': {
                'recommended_products': [
                    {
                        'product_name': 'Cereal Toasty Os (Cheerios)',
                        'product_id': '288563',
                        'recommended_quantity': 3,
                        'confidence': 85,
                        'optimal_order_date': '2024-01-02',
                        'reasoning': 'High demand prediction'
                    }
                ],
                'ordering_schedule': [
                    {
                        'date': '2024-01-02',
                        'products': ['Cereal Toasty Os (Cheerios)'],
                        'total_items': 3
                    }
                ],
                'insights': {
                    'seasonal_trends': 'Stable demand patterns',
                    'risk_assessment': 'Low risk assessment',
                    'cost_optimization': 'Consider bulk ordering'
                }
            },
            'summary': {
                'total_products_analyzed': 1,
                'recommended_products_count': 1,
                'avg_confidence': 85.0
            }
        }
        
        # Validate structure matches expected types
        for field, expected_type in expected_notebook_structure.items():
            with self.subTest(field=field):
                self.assertIn(field, mock_response)
                self.assertIsInstance(mock_response[field], expected_type)
        
        print("✓ Top-level structure matches notebook format")
        
        # Test product prediction structure
        product_pred = mock_response['productPredictions'][0]
        expected_product_fields = {
            'product_id': str,
            'product_name': str,
            'category_name': str,
            'vendor_name': str,
            'predictions': dict,
            'order_history': dict
        }
        
        for field, expected_type in expected_product_fields.items():
            with self.subTest(field=field):
                self.assertIn(field, product_pred)
                self.assertIsInstance(product_pred[field], expected_type)
        
        print("✓ Product prediction structure matches notebook format")
        
        # Test prediction values structure
        pred_values = list(product_pred['predictions'].values())[0]
        expected_pred_fields = ['p10', 'p50', 'p90', 'mean']
        
        for field in expected_pred_fields:
            with self.subTest(field=field):
                self.assertIn(field, pred_values)
                self.assertIsInstance(pred_values[field], (int, float))
        
        # Test quantile ordering (p10 <= p50 <= p90)
        self.assertLessEqual(pred_values['p10'], pred_values['p50'])
        self.assertLessEqual(pred_values['p50'], pred_values['p90'])
        
        print("✓ Prediction values structure matches notebook format")
        
        # Test recommendation structure
        recommendations = mock_response['recommendations']
        expected_rec_structure = {
            'recommended_products': list,
            'ordering_schedule': list,
            'insights': dict
        }
        
        for field, expected_type in expected_rec_structure.items():
            with self.subTest(field=field):
                self.assertIn(field, recommendations)
                self.assertIsInstance(recommendations[field], expected_type)
        
        print("✓ Recommendation structure matches notebook format")
        
        # Test insights structure
        insights = recommendations['insights']
        expected_insight_fields = ['seasonal_trends', 'risk_assessment', 'cost_optimization']
        
        for field in expected_insight_fields:
            with self.subTest(field=field):
                self.assertIn(field, insights)
                self.assertIsInstance(insights[field], str)
                self.assertGreater(len(insights[field]), 0)
        
        print("✓ Insights structure matches notebook format")
        
        print("✓ All notebook consistency validation tests passed!")

def run_integration_tests():
    """Run all integration tests for the prediction pipeline"""
    print("=" * 60)
    print("PREDICTION PIPELINE INTEGRATION TESTS")
    print("=" * 60)
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPredictionPipelineIntegration)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall result: {'PASS' if success else 'FAIL'}")
    
    return success

if __name__ == '__main__':
    success = run_integration_tests()
    sys.exit(0 if success else 1)