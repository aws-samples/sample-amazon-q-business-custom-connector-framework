# Instructions for Amazon Q Developer Agent

As an expert at building custom connectors for Amazon Q Business, you must thoroughly read and understand ALL of the following files and ALL lines before creating a custom connector for Amazon Q Business using the Custom Connector Framework.

## 🚨 CRITICAL: READ ALL FILES IN EXACT ORDER 🚨

**DO NOT SKIP ANY FILES. READ EVERY SINGLE ONE COMPLETELY BEFORE PROCEEDING TO THE NEXT SECTION.**

### Phase 0: Core Project Description (READ ALL BEFORE PROCEEDING TO PHASE 1)
1. `README.md` -> This file is in the project root

### Phase 1: Infrastructure Files (READ ALL BEFORE PROCEEDING TO PHASE 2)
2. `./custom-connector-framework-infrastructure/README.md`
3. `./custom-connector-framework-infrastructure/cdk/README.md`
4. `./custom-connector-framework-infrastructure/lambdas/README.md`
5. `./custom-connector-framework-infrastructure/lambdas/src/job_orchestrator_handler.py`
6. `./custom-connector-framework-infrastructure/cdk/model/README.md`
7. `./docs/CustomConnectorFrameworkOpenApiSpec.json`


### Phase 2: Builder Kit Files (READ ALL BEFORE PROCEEDING TO PHASE 3)
8. `./custom-connector-framework-builder-kit/README.md`
9. `./custom-connector-framework-builder-kit/src/custom_connector_framework/base_custom_connector_interfaces.py`
10. `./custom-connector-framework-builder-kit/src/custom_connector_framework/custom_connector_interface.py`
11. `./custom-connector-framework-builder-kit/src/custom_connector_framework/ccf_client.py`
12. `./custom-connector-framework-builder-kit/src/custom_connector_framework/models/document.py`
13. `./custom-connector-framework-builder-kit/src/custom_connector_framework/models/qbusiness.py`
14. `./custom-connector-framework-builder-kit/src/custom_connector_framework/types.py`

### Phase 3: Example Files (READ ALL BEFORE STARTING IMPLEMENTATION)
15. `./custom-connector-framework-builder-kit/examples/cdk/README.md`
16. `./custom-connector-framework-builder-kit/examples/gitlab/README.md`
17. `./custom-connector-framework-builder-kit/examples/web_crawler/README.md`
18. `./custom-connector-framework-builder-kit/examples/gitlab/custom_connector_cli.py`
19. `./custom-connector-framework-builder-kit/examples/web_crawler/custom_connector_cli.py`
20. `./custom-connector-framework-builder-kit/examples/cdk/lib/stacks/base-connector-stack.ts`
21. `./custom-connector-framework-builder-kit/examples/cdk/lib/stacks/gitlab-connector-stack.ts`
22. `./custom-connector-framework-builder-kit/examples/cdk/lib/stacks/web-crawler-connector-stack.ts`
23. `./custom-connector-framework-builder-kit/examples/cdk/bin/app.ts`

**CHECKPOINT**: After reading all files above, confirm you understand:
- The CCF architecture and components
- The builder kit interface and models
- How existing examples are structured
- The deployment patterns used

**ONLY AFTER READING ALL FILES ABOVE** should you proceed with implementation.

When a user requests a custom connector implementation, you must:
1. Perform a web search about the data source
2. Research its APIs, authentication methods, and data structures
3. Generate complete, production-ready code following the framework patterns

## Research and Analysis Phase

1. **Web Search Requirements**
   - Research the data source's official documentation
   - Identify available APIs and SDKs
   - Understand rate limits and quotas
   - Find Python client libraries if available
   - Review authentication methods

2. **Data Source Analysis**
   - Document structure and relationships
   - Available metadata and attributes
   - User and permission models
   - Change tracking capabilities
   - API endpoints and methods

3. **Authentication Analysis**
   - Focus on application-to-application auth methods
   - Identify most secure authentication option
   - Review token management requirements
   - Understand credential storage needs

## Project Structure

```
custom-connector-framework-builder-kit/examples/[DATA_SOURCE_NAME]/
├── src/
│   └── custom_connector_cli.py  # Main implementation
├── tests/
│   ├── __init__.py
│   └── test_[data_source_name]_connector.py
├── requirements.txt             # Production dependencies
├── requirements-dev.txt        # Development dependencies
├── config.json                 # Configuration template
├── README.md                   # Documentation
└── Makefile                    # Build and test commands
```

Certainly. Let's continue with the implementation requirements:

## Implementation Requirements

### 1. Document Modeling

- Study and utilize the models in `/custom-connector-framework-builder-kit/src/custom_connector_framework/models/document.py`
- Implement the following classes correctly:
  - `Document`
  - `DocumentMetadata`
  - `DocumentFile`
- Ensure all relevant data from the source system is mapped to these structures
- Maximize searchability by using appropriate fields and metadata

### 2. Access Control

- Implement access controls using models from `/custom-connector-framework-builder-kit/src/custom_connector_framework/models/qbusiness.py`
- Correctly use:
  - `AccessControl`
  - `Principal`
  - `PrincipalUser`
- Map source system permissions to Q Business access controls
- Ensure every document has appropriate access controls

### 3. Core Implementation (`custom_connector_cli.py`)

- Implement `QBusinessCustomConnectorInterface`
- Handle authentication securely
- Implement document processing and indexing
- Manage access control mapping
- Implement efficient change detection and incremental sync
- Use `CCFClient` for checkpoint management and framework integration

### 4. Error Handling and Logging

- Implement comprehensive error handling
- Use structured logging with appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Handle rate limiting and network issues gracefully

### 5. Testing (`test_[data_source_name]_connector.py`)

- Write comprehensive unit tests
- Mock external dependencies
- Test error scenarios and edge cases
- Aim for >80% test coverage
- Include integration tests for end-to-end functionality

### 6. Configuration (`config.json`)

- Create a template for static configurations
- Use environment variables for sensitive information
- Document all configuration options in the README

### 7. Documentation (`README.md`)

- Provide clear setup instructions
- Include usage guide and examples
- List all configuration options and environment variables
- Add a troubleshooting section
- Document any data source-specific considerations

### 8. Makefile

Include targets for:
- `install`: Set up development environment
- `test`: Run all tests
- `format`: Auto-format code
- `lint`: Run linters
- `validate`: Run type checking

### 9. CDK Integration

- Create a new stack extending `BaseConnectorStack`
- Configure environment variables and permissions
- Ensure correct entry point specification
- Update `/custom-connector-framework-builder-kit/examples/cdk/bin/app.ts`

## Critical Requirements

1. CCF Client Configuration
   - Use `CCF_ENDPOINT_URL` environment variable
   - Initialize client with correct endpoint and region

2. Performance Considerations
   - Implement batching for large datasets
   - Use checkpoints for efficient incremental syncs
   - Consider memory usage and processing time

3. Security
   - Never hardcode credentials
   - Use secure methods for storing and accessing secrets
   - Implement proper error handling to avoid information leakage

## Validation and Testing

Before delivery:
1. Run all tests: `make test`
2. Ensure code quality: `make format` and `make lint`
3. Verify CDK deployment locally
4. Test the connector with sample data
5. Validate all configuration options

## Delivery Checklist

- [ ] Complete `custom_connector_cli.py` implementation
- [ ] Comprehensive unit and integration tests (at least 80% test coverage)
- [ ] `config.json` with all necessary options
- [ ] `requirements.txt` and `requirements-dev.txt`
- [ ] Detailed README.md
- [ ] Makefile with required targets
- [ ] CDK stack implementation
- [ ] Passed all tests and quality checks

Remember to maintain a professional coding style, use type hints, and follow all best practices outlined in the framework documentation. Your implementation should be production-ready and easily maintainable.
