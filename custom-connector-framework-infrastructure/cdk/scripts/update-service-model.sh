#!/bin/bash
set -e

# Get the API ID from the CDK output
echo "Getting API Gateway ID from CloudFormation outputs..."
API_ID=$(aws cloudformation describe-stacks --stack-name CustomConnectorFrameworkStack --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayId'].OutputValue" --output text)

if [ -z "$API_ID" ]; then
    echo "Error: Could not retrieve API Gateway ID from CloudFormation outputs."
    exit 1
fi

echo "Found API Gateway ID: $API_ID"

# Create model directory if it doesn't exist
MODEL_DIR="model"
mkdir -p "$MODEL_DIR"

# Export the OpenAPI specification from API Gateway
echo "Exporting OpenAPI specification from API Gateway..."
OPENAPI_FILE="$MODEL_DIR/CustomConnectorFramework-prod-oas30.json"
aws apigateway get-export \
    --rest-api-id "$API_ID" \
    --stage-name prod \
    --export-type oas30 \
    --accepts application/json \
    --no-cli-pager \
    "$OPENAPI_FILE"

if [ ! -f "$OPENAPI_FILE" ]; then
    echo "Error: Failed to export OpenAPI specification."
    exit 1
fi

echo "OpenAPI specification exported to $OPENAPI_FILE"

# Get the API Gateway endpoint URL
API_URL=$(aws apigateway get-stage --rest-api-id "$API_ID" --stage-name prod --query "invokeUrl" --output text)
if [ -z "$API_URL" ]; then
    echo "Warning: Could not retrieve API Gateway endpoint URL."
    # Try alternative method
    API_URL="https://$API_ID.execute-api.$(aws configure get region).amazonaws.com/prod"
    echo "Using constructed URL: $API_URL"
fi

# Add servers section to OpenAPI spec
echo "Adding servers section to OpenAPI spec..."
TMP_FILE=$(mktemp)
jq --arg url "$API_URL" '. + {servers: [{url: $url}]}' "$OPENAPI_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$OPENAPI_FILE"

# Convert OpenAPI to service model
echo "Converting OpenAPI specification to AWS service model..."
cd "$MODEL_DIR"
python openapi_to_service_model.py CustomConnectorFramework-prod-oas30.json ccf

# Check if the service model was created
SERVICE_MODEL_FILE="ccf-service-model.json"
if [ ! -f "$SERVICE_MODEL_FILE" ]; then
    echo "Error: Failed to create service model."
    exit 1
fi

echo "Service model created at $SERVICE_MODEL_FILE"

# Register the service model with AWS CLI
echo "Registering service model with AWS CLI..."
aws configure add-model --service-model "file://$SERVICE_MODEL_FILE" --service-name ccf --no-cli-pager

echo "Service model successfully registered with AWS CLI."

# Create a sanitized version of the OpenAPI spec for documentation
echo "Creating sanitized OpenAPI spec for documentation..."
cd ..
DOCS_DIR="../../docs"
mkdir -p "$DOCS_DIR"

# Create a sanitized version by removing sensitive information
TMP_FILE=$(mktemp)
jq 'del(.servers) | del(.["x-amazon-apigateway-endpoint-configuration"]) | del(.["x-amazon-apigateway-policy"])' "$MODEL_DIR/CustomConnectorFramework-prod-oas30.json" > "$TMP_FILE"

# Remove URIs from x-amazon-apigateway-integration sections
python - "$TMP_FILE" <<EOF
import json
import sys

# Load the OpenAPI spec
with open(sys.argv[1], 'r') as f:
    spec = json.load(f)

# Remove URIs from x-amazon-apigateway-integration sections
if 'paths' in spec:
    for path, path_item in spec['paths'].items():
        for method, operation in path_item.items():
            if isinstance(operation, dict) and 'x-amazon-apigateway-integration' in operation:
                if 'uri' in operation['x-amazon-apigateway-integration']:
                    del operation['x-amazon-apigateway-integration']['uri']

# Write the sanitized spec back to the file
with open(sys.argv[1], 'w') as f:
    json.dump(spec, f, indent=2)
EOF

# Move the sanitized spec to the docs directory
mv "$TMP_FILE" "$DOCS_DIR/CustomConnectorFrameworkOpenApiSpec.json"

echo "Sanitized OpenAPI spec saved to $DOCS_DIR/CustomConnectorFrameworkOpenApiSpec.json"
echo "You can now use 'aws ccf' commands or boto3 client('ccf') to interact with the Custom Connector Framework API."
