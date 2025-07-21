# Custom Connector Framework Examples CDK

This directory contains AWS CDK code for deploying and scheduling custom connectors using the Custom Connector Framework.

## Overview

As a connector builder you need to worry about two major aspects:

1. Building the custom connector code. This can leverage the Python builder kit, but is entirely optional.
2. Running your code in a deployed environment.

This CDK project utilizes the Custom Connector Framework APIs to create/update a custom connector and schedule the custom connector job. In order to create a custom connector you need a container image packaged with your code, an execution role, and a job role. Please refer to the [Custom Connector Framework documentation](../../../custom-connector-framework-infrastructure/README.md) for more information. In addition to using the APIs, we simplify the process of creating the roles and uploading the container image to Elastic Container Service (ECS). Lastly, we provide ready to deploy examples to get started.

## Prerequisites

- [Node.js](https://nodejs.org/) (v18 or later)
- [AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html) installed and configured
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials
- [Docker](https://docs.docker.com/get-docker/) installed and running
- [Python](https://www.python.org/downloads/) (3.12 or later) for connector development
- Custom Connector Framework deployed in your AWS account
- Amazon Q Business application with a custom data source

## Directory Structure

```
cdk/
├── bin/
│   └── app.ts                # CDK application entry point
├── lib/
│   ├── stacks/
│   │   ├── base-connector-stack.ts    # Base stack with shared resources
│   │   ├── gitlab-connector-stack.ts  # Example GitLab connector stack
│   │   └── web-crawler-connector-stack.ts  # Example Web crawler connector stack
│   └── utils/
│       └── file-utils.ts     # Utilities for file operations
├── lambdas/
│   └── src/                  # Lambda functions for connector management
├── package.json
├── tsconfig.json
└── cdk.json
```

## Installation

```bash
# Install dependencies
npm install
```

## Docker Authentication

Before deploying, you must authenticate Docker with AWS Public ECR to pull the Lambda base images:

```bash
# Authenticate Docker with AWS Public ECR
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
```

**Note**: This authentication is required because the CDK deployment builds Docker images that use AWS Lambda base images from the public ECR registry (`public.ecr.aws/lambda/python:3.12`). Without authentication, you'll encounter a "403 Forbidden" error during the Docker build process.

## Configuration

Before deploying, set the environment variables for the connector stacks you wish to deploy. The stacks are optional and will only be deployed when all required configurations are provided.

### Required Environment Variables

For the Web Crawler Connector:

```bash
export CCF_ENDPOINT="https://<your-id>.execute-api.<your-region>.amazonaws.com/prod/"
export WEB_CRAWLER_Q_BUSINESS_APP_ID="your-app-id"
export WEB_CRAWLER_Q_BUSINESS_INDEX_ID="your-index-id"
export WEB_CRAWLER_Q_Q_BUSINESS_DATA_SOURCE_ID="your-data-source-id"
```

For the GitLab Connector:

```bash
export CCF_ENDPOINT="https://<your-id>.execute-api.<your-region>.amazonaws.com/prod/"
export GITLAB_Q_BUSINESS_APP_ID="your-app-id"
export GITLAB_Q_BUSINESS_INDEX_ID="your-index-id"
export GITLAB_Q_BUSINESS_DATA_SOURCE_ID="your-data-source-id"
export GITLAB_TOKEN="your-gitlab-token"
export GITLAB_URL="https://gitlab.com"  # Optional, defaults to https://gitlab.com
```

## Creating Secrets

For the GitLab connector, the GitLab API token should be provided via environment variable:

```bash
export GITLAB_TOKEN="your-gitlab-token"
```

The token will be automatically stored in AWS Secrets Manager when the GitLab connector stack is deployed.

## Deployment

```bash
# First, authenticate Docker with AWS Public ECR (required for base image access)
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws

# Deploy all configured stacks
npm run cdk deploy --all

# Deploy specific connector stack (if configured)
npm run cdk deploy GitLabConnectorStack
npm run cdk deploy WebCrawlerConnectorStack
```

**Important**: The Docker authentication step must be completed before deployment, otherwise the CDK will fail to build the connector Docker images with a "403 Forbidden" error when accessing the AWS Lambda base images.

Note: Attempting to deploy a stack without its required configurations will result in the stack being skipped with a console message.

## Stack Details

### Base Connector Stack

The base connector stack (`BaseConnectorStack`) provides shared functionality:

- Docker image building from connector code
- IAM roles and policies for connector execution
- Custom connector registration with the CCF API
- EventBridge rules for scheduled execution

### GitLab Connector Stack

The GitLab connector stack (`GitLabConnectorStack`) provisions:

- Custom connector for GitLab integration
- Secure storage of GitLab API token in Secrets Manager
- Daily scheduled execution via EventBridge
- IAM permissions for Amazon Q Business integration

### Web Crawler Connector Stack

The Web crawler connector stack (`WebCrawlerConnectorStack`) provisions:

- Custom connector for web crawling
- Daily scheduled execution via EventBridge
- IAM permissions for Amazon Q Business integration

## Customization

### Adding a New Connector

1. Create a new stack file in the `lib/stacks` directory:

```typescript
import { Construct } from "constructs";
import { BaseConnectorStack } from "./base-connector-stack";

export interface MyConnectorStackProps {
  ccfEndpoint: string;
  qBusinessAppId: string;
  qBusinessIndexId: string;
  qBusinessDataSourceId: string;
  // Add connector-specific properties
}

export class MyConnectorStack extends BaseConnectorStack {
  constructor(scope: Construct, id: string, props: MyConnectorStackProps) {
    super(scope, id, {
      connectorName: "my-connector",
      connectorDescription: "My Custom Connector",
      connectorPath: "/path/to/connector/code",
      entryPoint: ["python", "custom_connector_cli.py"],
      ccfEndpoint: props.ccfEndpoint,
      memory: 2048,
      cpu: 1,
      timeout: 900,
      qBusinessConfig: {
        applicationId: props.qBusinessAppId,
      },
      environmentVariables: {
        Q_BUSINESS_APP_ID: props.qBusinessAppId,
        Q_BUSINESS_INDEX_ID: props.qBusinessIndexId,
        Q_BUSINESS_DATA_SOURCE_ID: props.qBusinessDataSourceId,
        // Add connector-specific environment variables
      },
    });
  }
}
```

2. Add the new stack to `bin/app.ts`:

```typescript
import { App } from "aws-cdk-lib";
import { MyConnectorStack } from "../lib/stacks/my-connector-stack";

const app = new App();

// Deploy My Custom connector
new MyConnectorStack(app, "MyConnectorStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
  ccfEndpoint,
  qBusinessAppId: "your-app-id",
  qBusinessIndexId: "your-index-id",
  qBusinessDataSourceId: "your-data-source-id",
  // Add connector-specific configuration
});
```

### Modifying Schedule

To change the execution schedule, update the `schedule` parameter in the connector stack:

```typescript
import { Duration } from 'aws-cdk-lib';
import { Schedule } from 'aws-cdk-lib/aws-events';

// Daily at noon
schedule: Schedule.rate(Duration.days(1)),

// Or use cron expression
// schedule: Schedule.expression('cron(0 12 * * ? *)'),
```

## Monitoring and Troubleshooting

### Common Issues

#### Docker Authentication Error

If you encounter a "403 Forbidden" error during deployment like:

```
ERROR: unexpected status from HEAD request to https://public.ecr.aws/v2/lambda/python/manifests/3.12: 403 Forbidden
```

**Solution**: Authenticate Docker with AWS Public ECR:

```bash
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
```

#### Docker Not Running

If you see Docker-related errors, ensure Docker is installed and running:

```bash
# Check if Docker is running
docker --version
docker info
```

### Monitoring Resources

- **CloudWatch Logs**: All connector jobs output logs to CloudWatch.
- **AWS Batch Console**: Monitor job status and execution details
- **Custom Connector Framework API**: Use the CCF API to check connector and job status

## Additional Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/latest/guide/home.html)
- [AWS Batch Documentation](https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html)
- [EventBridge Scheduler Documentation](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-run-schedules.html)
- [Custom Connector Framework Documentation](../../../README.md)
- [Builder Kit Documentation](../../README.md)
