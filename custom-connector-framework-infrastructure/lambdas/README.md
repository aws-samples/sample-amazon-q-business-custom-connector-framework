# Amazon Q Business Custom Connector Framework Lambda Functions

Lambda functions that power the Amazon Q Business Custom Connector Framework API and job orchestration.

## Overview

These Lambda functions handle various aspects of the Custom Connector Framework:

1. **API Handler** (`src/api_handler.py`): 
   - Processes all API requests
   - Manages custom connectors, jobs, documents, and checkpoints
   - Interacts with DynamoDB tables to store and retrieve data

2. **Job Orchestrator Handler** (`src/job_orchestrator_handler.py`):
   - Triggered by DynamoDB Streams when job entries are created or updated
   - Submits jobs to AWS Batch for execution
   - Handles job cancellation requests

3. **Job Status Handler** (`src/job_status_handler.py`):
   - Triggered by EventBridge events when AWS Batch jobs complete
   - Updates job status in DynamoDB
   - Sets custom connector status back to AVAILABLE when jobs complete

## Prerequisites

- [Python 3.11](https://www.python.org/downloads/) or later
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials

## Installation

The project uses a Makefile to simplify common development tasks:

```bash
# Create a virtual environment and install dependencies
make install
```

This command:
- Creates a Python virtual environment in `.venv/`
- Installs dependencies

## Directory Structure

```
lambdas/
├── bin/                  # Helper scripts
├── src/                  # Source code for Lambda functions
│   ├── activities/       # Business logic for API operations
│   ├── common/           # Shared utilities, DAOs, and models
│   ├── api_handler.py    # Main API handler
│   ├── job_orchestrator_handler.py  # Job orchestration handler
│   └── job_status_handler.py        # Job status update handler
└── tests/                # Unit tests
```

## Development

### Running Tests

```bash
# Run unit tests with coverage reporting
make test

# Run integration tests against deployed CCF API
make integ
```

### Code Formatting and Linting

```bash
# Format and lint code
make format

# Run type checking
make validate
```

### Cleaning Up

```bash
# Clean up build artifacts and caches
make clean
```

## Deployment

The Lambda functions are deployed as part of the CDK stack. See the [CDK README](../cdk/README.md) for deployment instructions.

## Additional Resources

- [Infrastructure Overview](../README.md)
- [Main Framework Documentation](../../README.md)
- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)
- [Python AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html)
