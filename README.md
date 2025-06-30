# Enhanced Order Prediction Solution

A comprehensive AWS-based solution for predicting customer orders using Amazon Forecast and Amazon Bedrock, with enhanced product-level forecasting capabilities.

## 🚀 Features

### Core Capabilities
- **Automated Data Processing**: Intelligent feature engineering with temporal and product-level features
- **Product-Level Forecasting**: Individual product demand prediction for better inventory management
- **AI-Enhanced Insights**: Amazon Bedrock integration for intelligent recommendations
- **Real-time APIs**: RESTful endpoints for predictions and recommendations
- **Feedback Loop**: Continuous learning through user feedback collection
- **Data Validation**: Automated data quality checks and validation
- **Monitoring**: CloudWatch alarms and comprehensive logging

### New Enhancements
- **Enhanced Feature Engineering**: Advanced temporal features, cyclical encoding, and product categorization
- **Product Lookup System**: DynamoDB-based product catalog with customer-facility relationships
- **Prediction Caching**: Performance optimization through intelligent caching
- **Multi-level Forecasting**: Both aggregate and product-level predictions
- **Recommendation Engine**: AI-powered product recommendations for reordering and new products

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Raw Data      │    │   Enhanced       │    │   Amazon        │
│   (S3 Bucket)   │───▶│   Feature Eng.   │───▶│   Forecast      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Product       │    │   Data           │    │   Enhanced      │
│   Lookup (DDB)  │◀───│   Validation     │    │   Predictions   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   API Gateway   │◀───│   Prediction     │◀───│   Amazon        │
│   (REST APIs)   │    │   Cache (DDB)    │    │   Bedrock       │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📋 Prerequisites

- AWS CLI installed and configured
- SAM CLI installed
- Python 3.9 or higher
- jq (for parsing JSON outputs)
- Valid AWS credentials with appropriate permissions

### Required AWS Permissions
- Amazon S3 (full access)
- Amazon DynamoDB (full access)
- Amazon Forecast (full access)
- Amazon Bedrock (invoke model permissions)
- AWS Lambda (full access)
- Amazon API Gateway (full access)
- AWS CloudFormation (full access)
- AWS IAM (role creation permissions)

## 🚀 Quick Start

### 1. Clone and Deploy

```bash
# Extract the deployment package
unzip procurement_partners_deployment_package.zip
cd procurement_partners_deployment_package

# Deploy with default settings
./deploy.sh

# Or deploy with custom settings
./deploy.sh --stack-name my-order-prediction \
           --region us-east-1 \
           --environment prod \
           --bedrock-model anthropic.claude-3-7-sonnet-20250219-v1:0
```

### 2. Upload Sample Data

```bash
# Upload your historical order data
aws s3 cp your-order-data.csv s3://order-prediction-raw-data-{ACCOUNT-ID}-{ENV}/
```

### 3. Test the APIs

```bash
# Get aggregate predictions
curl "https://{API-ID}.execute-api.{REGION}.amazonaws.com/Prod/predict?customerId=CUST001&facilityId=FAC001"

# Get product-level predictions
curl "https://{API-ID}.execute-api.{REGION}.amazonaws.com/Prod/predict/products?customerId=CUST001&facilityId=FAC001"

# Get recommendations
curl "https://{API-ID}.execute-api.{REGION}.amazonaws.com/Prod/recommend?customerId=CUST001&facilityId=FAC001&type=reorder"
```

## 📊 Data Format

### Input Data Schema

Your CSV files should contain the following columns:

```csv
CreateDate,CustomerID,FacilityID,ProductID,Quantity,UnitPrice,ProductCategory,ProductDescription
2025-01-01,CUST001,FAC001,PROD001,100,25.50,Electronics,Widget A
2025-01-02,CUST001,FAC001,PROD002,50,15.75,Office Supplies,Paper Clips
```

### Required Columns
- `CreateDate`: Order date (YYYY-MM-DD format)
- `CustomerID`: Unique customer identifier
- `FacilityID`: Customer facility identifier
- `ProductID`: Product identifier
- `Quantity`: Order quantity (numeric)

### Optional Columns (for enhanced features)
- `UnitPrice`: Product unit price
- `ProductCategory`: Product category
- `ProductDescription`: Product description
- `SeasonalFlag`: Seasonal indicator (Y/N)

## 🔧 Configuration

### Environment Variables

The solution supports the following configuration options:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `Environment` | `dev` | Deployment environment (dev/test/prod) |
| `BedrockModelId` | `anthropic.claude-3-7-sonnet-20250219-v1:0` | Bedrock model for AI insights |
| `EnableProductLevelForecasting` | `true` | Enable product-level predictions |

### Customization

You can customize the solution by modifying:

1. **Feature Engineering**: Edit `functions/enhanced_feature_engineering/app.py`
2. **Prediction Logic**: Edit `functions/enhanced_predictions/app.py`
3. **API Responses**: Edit the respective API function files
4. **CloudFormation Template**: Edit `template.yaml`

## 📈 API Reference

### Prediction Endpoints

#### GET /predict
Get aggregate order predictions for a customer facility.

**Parameters:**
- `customerId` (required): Customer identifier
- `facilityId` (required): Facility identifier

**Response:**
```json
{
  "predictions": [
    {
      "date": "2025-07-01",
      "predicted_quantity": 150.5,
      "confidence_interval": {
        "lower": 120.0,
        "upper": 180.0
      }
    }
  ],
  "insights": "Based on historical patterns, expect 15% increase in July orders."
}
```

#### GET /predict/products
Get product-level predictions.

**Parameters:**
- `customerId` (required): Customer identifier
- `facilityId` (required): Facility identifier
- `productId` (optional): Specific product ID

**Response:**
```json
{
  "product_predictions": [
    {
      "product_id": "PROD001",
      "product_name": "Widget A",
      "predictions": [
        {
          "date": "2025-07-01",
          "predicted_quantity": 75.0,
          "confidence": 0.85
        }
      ]
    }
  ]
}
```

#### GET /recommend
Get AI-powered product recommendations.

**Parameters:**
- `customerId` (required): Customer identifier
- `facilityId` (required): Facility identifier
- `type` (optional): Recommendation type (`reorder`, `new_products`, `seasonal`)

**Response:**
```json
{
  "recommendations": [
    {
      "product_id": "PROD001",
      "product_name": "Widget A",
      "recommendation_type": "reorder",
      "suggested_quantity": 100,
      "reason": "Due for reorder based on consumption pattern",
      "confidence": 0.9
    }
  ]
}
```

#### POST /feedback
Submit feedback on predictions.

**Request Body:**
```json
{
  "customer_id": "CUST001",
  "facility_id": "FAC001",
  "prediction_id": "pred-123",
  "feedback_type": "accuracy",
  "rating": 4,
  "comments": "Prediction was close to actual demand",
  "actual_quantity": 145.0,
  "predicted_quantity": 150.5
}
```

## 🔍 Monitoring and Troubleshooting

### CloudWatch Logs

Monitor the solution using CloudWatch logs:

```bash
# View all logs
sam logs --stack-name cart-prediction --region us-east-1

# View specific function logs
aws logs tail /aws/lambda/cart-prediction-EnhancedFeatureEngineeringFunction --follow
```

### CloudWatch Alarms

The solution includes pre-configured alarms for:
- Lambda function errors
- API Gateway 4xx/5xx errors
- DynamoDB throttling

### Common Issues

1. **Data Processing Failures**
   - Check data format matches expected schema
   - Verify S3 bucket permissions
   - Review CloudWatch logs for specific errors

2. **Forecast Creation Issues**
   - Ensure sufficient historical data (minimum 100 data points)
   - Check Forecast service limits
   - Verify IAM permissions for Forecast service

3. **API Errors**
   - Verify API Gateway deployment
   - Check Lambda function permissions
   - Review request parameters

## 💰 Cost Optimization

### Estimated Monthly Costs (us-east-1)

| Service | Usage | Estimated Cost |
|---------|-------|----------------|
| Lambda | 1M requests, 512MB | $20 |
| API Gateway | 1M requests | $3.50 |
| DynamoDB | 1GB storage, 100 RCU/WCU | $25 |
| S3 | 10GB storage, 1000 requests | $2 |
| Forecast | 1 predictor, 1000 forecasts | $50 |
| Bedrock | 1M tokens | $15 |
| **Total** | | **~$115** |

### Cost Optimization Tips

1. **Use S3 Lifecycle Policies**: Automatically delete old data
2. **DynamoDB On-Demand**: Use on-demand billing for variable workloads
3. **Lambda Memory Optimization**: Right-size Lambda memory allocation
4. **Forecast Cleanup**: Delete unused predictors and forecasts
5. **API Caching**: Enable API Gateway caching for frequently accessed endpoints

## 🔒 Security Best Practices

### Implemented Security Features

- **IAM Least Privilege**: Functions have minimal required permissions
- **VPC Support**: Can be deployed in VPC for network isolation
- **Encryption**: All data encrypted at rest and in transit
- **API Authentication**: Support for API keys and IAM authentication
- **Input Validation**: Comprehensive input validation in all functions

### Additional Security Recommendations

1. **Enable AWS CloudTrail**: Monitor API calls and changes
2. **Use AWS WAF**: Protect API Gateway from common attacks
3. **Implement API Rate Limiting**: Prevent abuse and control costs
4. **Regular Security Reviews**: Audit IAM permissions and access patterns
5. **Data Classification**: Classify and protect sensitive data appropriately

## 🤝 Contributing

To contribute to this solution:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/

# Format code
black functions/
```

## 📞 Support

For support and questions:

1. **Documentation**: Check this README and inline code comments
2. **AWS Support**: Use AWS Support for service-specific issues
3. **CloudWatch Logs**: Check logs for detailed error information
4. **GitHub Issues**: Report bugs and feature requests

## 📄 License

This solution is provided under the MIT License. See LICENSE file for details.

## 🔄 Version History

### v2.0.0 (Current)
- Enhanced product-level forecasting
- AI-powered recommendations
- Improved feature engineering
- Performance optimizations
- Comprehensive monitoring

### v1.0.0
- Basic order prediction functionality
- Simple API endpoints
- Basic data processing

---

**Happy Forecasting! 🎯**
