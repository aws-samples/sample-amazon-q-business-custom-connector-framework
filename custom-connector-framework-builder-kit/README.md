# Amazon Q Business Custom Connector Framework Builder Kit

A Python package that simplifies the development of custom connectors for Amazon Q Business.

## Overview

The Builder Kit allows you to focus on the specific logic needed to connect to your data source, while the framework handles the complexities of:

- Document processing and transformation
- Access control management
- Document change detection
- Batching and size limitations
- Integration with the Custom Connector Framework (CCF)

## Prerequisites

- [Python 3.12](https://www.python.org/downloads/) or later
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials

## Installation

Install the Builder Kit package using pip locally:

```bash
pip install .
```

## Key Components
The following components are useful to understand when you get building. The most important are the interfaces, which are used to simplify the indexing your documents in Amazon Q Business.

### Interfaces

- **[QBusinessCustomConnectorInterface](./src/custom_connector_framework/custom_connector_interface.py)**: The main interface for building custom connectors that index data directly into your Amazon Q Business custom connector.
- **[BaseCustomConnectorInterface](./src/custom_connector_framework/base_custom_connector_interfaces.py)**: The base abstract class that provides common functionality for all connector types.

### Models

- **[Document](./src/custom_connector_framework/models/document.py)**: Represents a document to be indexed, including ID, file reference, and metadata
- **[DocumentMetadata](./src/custom_connector_framework/models/document.py)**: Contains metadata like title, source URI, attributes, and access controls
- **[AccessControl](./src/custom_connector_framework/models/qbusiness.py)**: Defines who can access a document in Amazon Q Business

### CCF Client

The [CCFClient](./src/custom_connector_framework/ccf_client.py) wraps the Custom Connector Framework APIs, enabling:

- Document change tracking through checksums
- State persistence between connector runs via checkpoints
- Document management within the Custom Connector Framework

## Usage

Here's a simple example of building a custom connector:

```python
from custom_connector_framework.custom_connector_interface import QBusinessCustomConnectorInterface
from custom_connector_framework.models.document import Document, DocumentFile, DocumentMetadata
from typing import Iterator

class MyCustomConnector(QBusinessCustomConnectorInterface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_documents_to_add(self) -> Iterator[Document]:
        # Your code to fetch and yield documents
        # Note you can add access controls to this as well, but they are optional. 
        fake_doc = Document(
            id="document-id-1",
            file=DocumentFile("/path/to/file.txt"),
            metadata=DocumentMetadata(
                title="Document Title",
                source_uri="https://example.com/document",
                attributes={"author": "Custom Connector Framework"}
            )
        )
        yield fake_doc

    def get_documents_to_delete(self) -> Iterator[str]:
        # Optional: Return IDs of documents to delete
        return iter(["document-id-to-delete"])
```

## Document Constraints

Amazon Q Business has the following limits for document indexing:

- Up to 10 documents per batch
- Up to 10MB total batch size for inline documents
- Documents >10MB must be uploaded to S3 (requires s3_client and s3_bucket)
- Documents >50MB will be skipped

## Development

The project uses a Makefile to simplify common development tasks:

```bash
# Run tests
make test

# Format code
make format

# Clean up
make clean
```

## Examples

The Builder Kit includes several example connectors using the builder kit:

- **[Web Crawler](./examples/web_crawler/)**: Indexes content from websites
- **[GitLab](./examples/gitlab/)**: Indexes repositories, issues, and merge requests from GitLab
- **[CDK Deployment](./examples/cdk/)**: Example CDK app for deploying custom connectors

## Additional Resources

- [Main Framework Documentation](../README.md)
- [Infrastructure Documentation](../custom-connector-framework-infrastructure/README.md)
- [Amazon Q Business Custom Connector Documentation](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/custom-connector.html)
