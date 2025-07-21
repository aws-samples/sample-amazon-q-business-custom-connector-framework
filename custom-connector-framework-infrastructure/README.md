# Amazon Q Business Custom Connector Framework Infrastructure

The infrastructure components for the Amazon Q Business Custom Connector Framework (CCF), providing APIs, storage, and compute resources to run custom connectors.

## Overview

The Custom Connector Framework Infrastructure provides:

1. **RESTful APIs**: API Gateway with AWS IAM authorization
2. **Lambda Functions**: For handling API requests, job orchestration, and status updates
3. **Storage**: DynamoDB tables for metadata about connectors, jobs, and documents
4. **Compute**: AWS Batch and Fargate for running custom connector jobs
5. **Events**: DynamoDB Streams and EventBridge for job lifecycle orchestration

## Prerequisites

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials
- [Node.js](https://nodejs.org/) (v18 or later) and npm
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html) installed (`npm install -g aws-cdk`)

## Installation

Navigate to the CDK directory and deploy the infrastructure:

```bash
cd custom-connector-framework-infrastructure/cdk
# Log into docker. We use bundling images to build the lambdas
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
npm install
npm run build
npm run deploy:full
```

This will:
- Deploy the CustomConnectorFrameworkStack to your AWS account
- Generate the boto3 client model for interacting with the CCF APIs

## Key Components

### Lambda Functions

1. **API Handler**: Processes all API requests and interacts with DynamoDB tables
2. **Job Orchestrator Handler**: Submits jobs to AWS Batch and handles job cancellations
3. **Job Status Handler**: Updates job status when AWS Batch jobs complete

## Development

For detailed development instructions, see the README files in the subdirectories:

- [CDK Infrastructure](./cdk/README.md)
- [Lambda Functions](./lambdas/README.md)

## Additional Resources

- [Main Framework Documentation](../README.md)
- [Builder Kit Documentation](../custom-connector-framework-builder-kit/README.md)
- [Builder Kit Examples](../custom-connector-framework-builder-kit/examples/)
- [Amazon Q Business Documentation](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/custom-connector.html)
