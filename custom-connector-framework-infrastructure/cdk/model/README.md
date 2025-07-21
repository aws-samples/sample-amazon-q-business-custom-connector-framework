# Custom Connector Framework Service Model

This directory contains tools for generating and using the AWS service model for the Custom Connector Framework.

## Overview

The Custom Connector Framework provides a REST API through API Gateway. To interact with this API using AWS CLI and boto3, we generate a service model that defines the API operations, request/response structures, and authentication requirements.

## Files

- `openapi_to_service_model.py`: Python script that converts an OpenAPI 3.0 specification to an AWS service model
- `boto3_example.py`: Example script demonstrating how to use boto3 with the Custom Connector Framework service model

## Generated Files (not checked into Git)

- `CustomConnectorFramework-prod-oas30.json`: OpenAPI 3.0 specification exported from API Gateway
- `ccf-service-model.json`: AWS service model generated from the OpenAPI specification

## Generating the Service Model

The service model is generated automatically after deployment using the `generate-model` script:

```bash
# From the cdk directory
npm run generate-model
```

This script:

1. Gets the API Gateway ID from CloudFormation outputs
2. Exports the OpenAPI specification from API Gateway
3. Converts it to an AWS service model using the `openapi_to_service_model.py` script
4. Registers the model with the AWS CLI

You can also run the full deployment and model generation in one command:

```bash
# From the cdk directory
npm run deploy:full
```

## Using the Service Model

After registering the service model, you can interact with the Custom Connector Framework API using:

### AWS CLI

```bash
# List custom connectors
aws ccf list-custom-connectors --endpoint-url https://<your-api-gw-id>.execute-api.<region>.amazonaws.com/prod

# Create a custom connector
aws ccf create-custom-connector \
  --name "ExampleConnector" \
  --description "Custom data source connector" \
  --container_properties '{
    "image_uri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-connector:latest",
    "execution_role_arn": "arn:aws:iam::123456789012:role/connector-execution-role",
    "job_role_arn": "arn:aws:iam::123456789012:role/connector-job-role"
  }' \
  --endpoint-url https://<your-api-gw-id>.execute-api.<region>.amazonaws.com/prod

# Start a connector job
aws ccf start-custom-connector-job \
  --connector-id "connector-123" \
  --environment '[
    {
      "name": "SOURCE_URL",
      "value": "https://example.com/data"
    }
  ]' \
  --endpoint-url https://<your-api-gw-id>.execute-api.<region>.amazonaws.com/prod
```

### boto3

```python
import boto3

# Initialize the CCF client
ccf_client = boto3.client(
    'ccf',
    region_name='us-east-1',
    endpoint_url='https://<your-api-gw-id>.execute-api.us-east-1.amazonaws.com/prod'
)

# List custom connectors
response = ccf_client.list_custom_connectors()
connectors = response.get('connectors', [])

# Create a custom connector
create_response = ccf_client.create_custom_connector(
    name="ExampleConnector",
    description="Custom data source connector",
    container_properties={
        "image_uri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-connector:latest",
        "execution_role_arn": "arn:aws:iam::123456789012:role/connector-execution-role",
        "job_role_arn": "arn:aws:iam::123456789012:role/connector-job-role"
    }
)

# Start a connector job
connector_id = "connector-123"
job_response = ccf_client.start_custom_connector_job(
    connector_id=connector_id,
    environment=[
        {
            "name": "SOURCE_URL",
            "value": "https://example.com/data"
        }
    ]
)
```

## Important Notes

- Always regenerate the service model after making changes to the API Gateway configuration
- The `name` parameter for connectors must match the pattern `^[a-zA-Z0-9-]+$` (only alphanumeric characters and hyphens)
- Always specify the `--endpoint-url` parameter when using the AWS CLI, as the service is not a standard AWS service
- When using boto3, make sure to provide the correct endpoint URL for your API Gateway deployment
- Note that parameter names use underscores (`--container_properties`) in the AWS CLI, not hyphens
- In boto3, parameter names also use underscores (`container_properties`)
