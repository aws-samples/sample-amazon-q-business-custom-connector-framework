# Amazon Q Business Custom Connector Framework CDK App

AWS CDK application for deploying the Amazon Q Business Custom Connector Framework infrastructure.

## Overview

This CDK application defines the infrastructure required to run the Custom Connector Framework, including:

1. **DynamoDB Tables**: Store metadata about connectors, jobs, and documents
2. **API Gateway**: Provides RESTful APIs for interacting with the framework
3. **Lambda Functions**: Process API requests and manage job lifecycle
4. **AWS Batch & Fargate**: Provide compute resources for running connector jobs
5. **VPC & Networking**: Configure the network environment for secure and isolated job execution
6. **IAM Roles & Policies**: Set up necessary permissions for all components

You can review the `CustomConnectorFrameworkStack` and resources in the following [file](lib/stacks/custom-connector-framework-stack.ts).

## Prerequisites

- AWS Account
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials
- [Node.js](https://nodejs.org/) (v18 or later) and npm
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html) installed (`npm install -g aws-cdk`)
- [Python](https://www.python.org/downloads/) (v3.12 or later)
- [Docker](https://docs.docker.com/get-docker/) installed and running (required for Lambda function bundling)

### Docker Authentication

If you encounter image pull errors, you may need to authenticate to Amazon ECR Public Gallery:

```bash
# Authenticate to ECR Public Gallery (use us-east-1 regardless of deployment region)
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
```

## Installation

```bash
# Install dependencies
npm install

# Build the TypeScript code
npm run build

# Deploy all stacks and generate boto3 client model
npm run deploy:full
```

## Configuration

You can customize the deployment by modifying the CDK context in `cdk.json` or by providing parameters during deployment:

```bash
# Deploy with specific parameters
cdk deploy --parameters vpcId=vpc-12345678
```

## Security Information

### Network Security

The framework creates the following network resources:

- **VPC**: A dedicated VPC with public and private subnets across 2 availability zones
- **NAT Gateways**: 2 NAT gateways to allow outbound internet access from private subnets
- **S3 Gateway Endpoint**: Allows private access to S3 without traversing the internet
- **Private Subnets**: All compute workloads (AWS Batch/Fargate) run in private subnets

If you provide an existing VPC ID, the framework will use that VPC instead of creating a new one.

### IAM Roles and Permissions

The framework creates several IAM roles with specific permissions:

1. **API Lambda Role**: Has permissions to:

   - Read/write to the DynamoDB tables
   - Write logs to CloudWatch

2. **Job Orchestrator Lambda Role**: Has permissions to:

   - Read/write to the DynamoDB tables
   - Submit, cancel, and describe AWS Batch jobs
   - Register job definitions
   - Access ECR repositories
   - Pass IAM roles to AWS services (with restrictions)
   - Read DynamoDB streams
   - Write logs to CloudWatch

3. **Job Status Lambda Role**: Has permissions to:

   - Read/write to the DynamoDB tables
   - Write logs to CloudWatch

4. **Batch Execution Role**: Has permissions to:
   - Pull container images
   - Write logs to CloudWatch

The IAM permissions follow the principle of least privilege where possible. The PassRole permission is scoped to exclude admin roles and IAM service.

> **IMPORTANT**: The framework includes PassRole permissions that allow passing IAM roles to AWS services. Framework adopters should carefully review and determine which specific roles need to be passed to ensure least privilege. Consider implementing IAM Permission Boundaries to restrict the maximum permissions that can be granted by users of the framework, preventing privilege escalation through role passing. This is especially important in multi-tenant environments or when the framework is used by multiple teams.

### API Security

The API Gateway is configured with:

- **IAM Authorization**: All API endpoints require AWS IAM authentication
- **Resource Policy**: Only the AWS account where the framework is deployed can invoke the API
- **Request Validation**: All requests are validated against JSON schemas
- **CORS**: Configured to allow cross-origin requests
- **Tracing**: AWS X-Ray tracing is enabled
- **Logging**: API Gateway access logs are enabled

## Resources with RETAIN Removal Policy

The following resources are created with `RemovalPolicy.RETAIN`, which means they will **not** be deleted when you destroy the CloudFormation stack:

1. **DynamoDB Tables**:
   - `CustomConnectors` - Stores connector metadata
   - `CustomConnectorJobs` - Stores job execution history
   - `CustomConnectorDocuments` - Stores document metadata and checksums

These resources are retained to preserve your data in case of accidental stack deletion. If you want to completely remove all resources, you will need to manually delete these DynamoDB tables after stack deletion.

## Stack Outputs

After deployment, the stack provides several outputs:

- **API Endpoint URL**: The URL for the Custom Connector Framework API
- **API ID**: The identifier for the API Gateway
- **Service Model Location**: Where the generated boto3 client model is stored
- **VPC ID**: The ID of the VPC created for the framework
- **Batch Job Queue**: The AWS Batch job queue for connector jobs

## Development

### Useful Commands

- `npm run build` - Compile TypeScript to JavaScript
- `npm run watch` - Watch for changes and compile
- `npm run test` - Perform the Jest unit tests
- `npm run lint` - Check code style
- `npm run format` - Format code using Prettier
- `npm run clean` - Clean build artifacts
- `npm run generate-model` - Generate boto3 client model

## Clean Up

```bash
# Destroy all stacks
npm run destroy
```

**Important**: As mentioned in the "Resources with RETAIN Removal Policy" section, some resources will not be automatically deleted. To completely clean up all resources:

1. Run the destroy command above
2. Manually delete the following DynamoDB tables in the AWS Console or using AWS CLI:
   - `CustomConnectors`
   - `CustomConnectorJobs`
   - `CustomConnectorDocuments`

```bash
# Manual cleanup of retained resources using AWS CLI
aws dynamodb delete-table --table-name CustomConnectors
aws dynamodb delete-table --table-name CustomConnectorJobs
aws dynamodb delete-table --table-name CustomConnectorDocuments
```

## Additional Resources

- [Infrastructure Overview](../README.md)
- [Main Framework Documentation](../../README.md)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
- [AWS Batch Documentation](https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html)
