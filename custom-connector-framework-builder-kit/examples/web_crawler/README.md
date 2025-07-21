# Web Crawler Connector for Amazon Q Business

A custom connector that indexes web content from specified URLs in Amazon Q Business.

## Prerequisites

- [Python 3.12](https://www.python.org/downloads/) or later
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials
- Amazon Q Business application with a custom data source

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Configuration

The connector is configured using a JSON file (`crawler_urls.json`):

```json
{
  "global_acl": {
    "member_relations": "OR",
    "principals": [
      {
        "user_id": "default-user@example.com",
        "access": "ALLOW",
        "membership_type": "INDEX"
      }
    ]
  },
  "urls": [
    {
      "url": "https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/create-application.html",
      "acl": {
        "member_relations": "OR",
        "principals": [
          {
            "user_id": "user1@example.com",
            "access": "ALLOW",
            "membership_type": "INDEX"
          },
          {
            "user_id": "user2@example.com",
            "access": "DENY",
            "membership_type": "INDEX"
          }
        ]
      }
    },
    {
      "url": "https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/create-application-iam.html"
    },
    {
      "url": "https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/custom-connector.html"
    }
  ]
}
```

## Usage

### Running Locally

```bash
export CRAWLER_CONFIG_PATH="crawler_urls.json"
export Q_BUSINESS_APP_ID="your-app-id"
export Q_BUSINESS_INDEX_ID="your-index-id"
export Q_BUSINESS_DATA_SOURCE_ID="your-data-source-id"
export AWS_REGION="us-east-1"
# Optional: For using the Custom Connector Framework
export CCF_ENDPOINT="https://your-api-gateway-id.execute-api.region.amazonaws.com/prod/"

python custom_connector_cli.py
```

### Deploying with CDK

See the [Examples CDK README](../cdk/README.md) for deployment instructions.

## Authentication Options

The web crawler uses the requests-html library for handling authentication. You'll need to modify the `custom_connector_cli.py` file to implement authentication for specific sites if needed.

## Access Control Configuration

The connector supports access control through the configuration file:

### Global Access Control

```json
"global_acl": {
  "member_relations": "OR",
  "principals": [
    {
      "user_id": "default-user@example.com",
      "access": "ALLOW",
      "membership_type": "INDEX"
    }
  ]
}
```

### URL-Specific Access Control

```json
"url": "https://example.com/page.html",
"acl": {
  "member_relations": "OR",
  "principals": [
    {
      "user_id": "user@example.com",
      "access": "ALLOW",
      "membership_type": "INDEX"
    }
  ]
}
```

## Content Extraction

The connector uses the requests-html library to extract content from web pages, with support for JavaScript rendering. It can handle both HTML and PDF content types.

## Security Considerations

- Store authentication credentials securely as secrets in AWS Secrets Manager
- Use a dedicated user account with minimal permissions for authenticated crawling
- Respect robots.txt and implement appropriate crawl delays to avoid overloading websites
- Consider legal implications of crawling and indexing third-party content

## Additional Resources

- [Builder Kit Documentation](../../README.md)
- [Examples CDK Documentation](../cdk/README.md)
- [Beautiful Soup Documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Amazon Q Business Documentation](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/custom-connector.html)
