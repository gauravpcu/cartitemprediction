# Lambda Layers Infrastructure

This directory contains the Lambda layer build infrastructure for optimizing AWS Lambda function deployments.

## Directory Structure

```
layers/
├── core-data-science/          # Core data science packages
│   ├── requirements.txt        # pandas, numpy, python-dateutil
│   └── python/                 # Built layer (auto-generated)
├── ml-libraries/               # Machine learning packages
│   ├── requirements.txt        # scikit-learn, joblib
│   └── python/                 # Built layer (auto-generated)
├── aws-utilities/              # AWS SDK packages
│   ├── requirements.txt        # boto3, botocore
│   └── python/                 # Built layer (auto-generated)
└── README.md                   # This file
```

## Layer Size Limits

- **core-data-science**: 100MB unzipped
- **ml-libraries**: 100MB unzipped  
- **aws-utilities**: 50MB unzipped

## Usage

### Build all layers
```bash
./scripts/manage-layers.sh build all
```

### Build specific layer
```bash
./scripts/manage-layers.sh build core-data-science
```

### Check layer status
```bash
./scripts/manage-layers.sh status
```

### Optimize layers (remove unnecessary files)
```bash
./scripts/manage-layers.sh optimize all
```

### Validate layers (size and imports)
```bash
./scripts/manage-layers.sh validate all
```

### Generate layer reports
```bash
./scripts/manage-layers.sh report all
```

### Clean build artifacts
```bash
./scripts/manage-layers.sh clean all
```

## Layer Contents

### Core Data Science Layer
- **pandas**: Data manipulation and analysis
- **numpy**: Numerical computing
- **python-dateutil**: Date/time utilities

### ML Libraries Layer
- **scikit-learn**: Machine learning library
- **joblib**: Parallel computing utilities

### AWS Utilities Layer
- **boto3**: AWS SDK for Python
- **botocore**: Core AWS SDK functionality

## Optimization Features

The build process automatically:
- Removes unnecessary files (*.pyc, __pycache__, tests, docs)
- Strips debug symbols and documentation
- Validates size constraints before deployment
- Optimizes package contents for Lambda runtime

## Integration with SAM Template

These layers are designed to be referenced in your SAM template:

```yaml
Layers:
  CoreDataScienceLayer:
    Type: AWS::Serverless::LayerVersion
    Properties:
      LayerName: core-data-science-layer
      ContentUri: layers/core-data-science/
      CompatibleRuntimes: [python3.9]
      
  MLLibrariesLayer:
    Type: AWS::Serverless::LayerVersion
    Properties:
      LayerName: ml-libraries-layer
      ContentUri: layers/ml-libraries/
      CompatibleRuntimes: [python3.9]
      
  AWSUtilitiesLayer:
    Type: AWS::Serverless::LayerVersion
    Properties:
      LayerName: aws-utilities-layer
      ContentUri: layers/aws-utilities/
      CompatibleRuntimes: [python3.9]
```