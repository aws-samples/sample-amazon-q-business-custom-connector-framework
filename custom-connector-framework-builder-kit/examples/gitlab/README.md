# GitLab Connector for Amazon Q Business

A custom connector that indexes GitLab repositories, issues, merge requests, and wikis in Amazon Q Business.

## Overview

This connector demonstrates how to use the Custom Connector Framework to index content from GitLab. It includes:

- Source code files from GitLab repositories
- Issues, merge requests, and wiki pages
- User permissions from GitLab projects
- Incremental syncing using checkpoints

## Prerequisites

- [Python 3.12](https://www.python.org/downloads/) or later
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with appropriate credentials
- GitLab account with API access
- Amazon Q Business application with a custom data source

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Configuration

The connector is configured using a JSON file (`gitlab_config.json`):

```json
{
  "gl_repositories_to_exclude": [
    "example/excluded-repo-1",
    "example/excluded-repo-2"
  ],
  "gl_file_extensions": [
    ".py", ".js", ".java", ".ts", ".go", ".rb", ".md", 
    ".json", ".yml", ".yaml", ".xml", ".html", ".css"
  ],
  "gl_excluded_paths": [
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "dist", "build", ".idea", ".vscode"
  ],
  "gl_include_issues": true,
  "gl_include_merge_requests": true,
  "gl_include_wiki": true,
  "gl_include_project_members": true,
  "gl_acl_missing_email_policy": "closed",
  "gl_max_projects": 50,
  "gl_default_branch_only": true
}
```

## Generating a GitLab Access Token

1. **Log in to GitLab**
   - Navigate to your GitLab instance (e.g., https://gitlab.com)

2. **Access User Settings**
   - Click on your profile avatar → Preferences

3. **Navigate to Access Tokens**
   - In the left sidebar, click on "Access Tokens"

4. **Create a New Token**
   - Fill in the following fields:
     - **Token name**: Enter a descriptive name (e.g., "Amazon Q Business Connector")
     - **Expiration date**: Set an expiration date or leave blank for a non-expiring token
     - **Scopes**: Select the appropriate permissions:
       - `read_api` - Required for basic API access
       - `read_repository` - Required to access repository files
       - `read_user` - Required to access user information
       - `read_project` - Required to access project metadata
       - `read_issues` (optional) - Required to index issues
       - `read_merge_requests` (optional) - Required to index merge requests
       - `read_wiki` (optional) - Required to index wiki pages

5. **Create the Token**
   - Click the "Create personal access token" button
   - **IMPORTANT**: Copy the generated token immediately and store it securely

## Usage

### Running Locally

```bash
export GITLAB_CONFIG_PATH="gitlab_config.json"
export Q_BUSINESS_APP_ID="your-app-id"
export Q_BUSINESS_INDEX_ID="your-index-id"
export Q_BUSINESS_DATA_SOURCE_ID="your-data-source-id"
export AWS_REGION="us-east-1"
export GITLAB_TOKEN="your-gitlab-token"
export GITLAB_URL="https://gitlab.com"
# Optional: For using the Custom Connector Framework
export CCF_ENDPOINT="https://your-api-gateway-id.execute-api.region.amazonaws.com/prod/"
# Alternative to GITLAB_TOKEN: Use a secret in AWS Secrets Manager
export GITLAB_TOKEN_SECRET_ARN="arn:aws:secretsmanager:region:account:secret:name"

python custom_connector_cli.py
```

### Deploying with CDK

See the [Examples CDK README](../cdk/README.md) for deployment instructions.

## Access Control Setup

The GitLab connector uses email addresses to map GitLab users to Amazon Q Business users. For this to work properly, users need to make their email addresses visible in GitLab:

1. **For individual users**:
   - Each user must set their email to public in their GitLab profile:
     1. Log in to GitLab
     2. Go to user settings (click on profile picture → Preferences)
     3. Navigate to "Public profile"
     4. Check the "Public email" option and select an email address
     5. Save changes

2. **Handling Missing Emails**:
   - `"gl_acl_missing_email_policy": "closed"` - Documents will be restricted if no users with public emails are found (more secure)
   - `"gl_acl_missing_email_policy": "open"` - Documents will be accessible to all Amazon Q Business users if no users with public emails are found (less secure)

## Security Considerations

- Store the GitLab API token securely as a secret in AWS Secrets Manager
- Use a token with the minimum required permissions
- Set an expiration date for the token and rotate it regularly
- Use a dedicated service account in GitLab for the connector

## Additional Resources

- [Builder Kit Documentation](../../README.md)
- [Examples CDK Documentation](../cdk/README.md)
- [GitLab API Documentation](https://docs.gitlab.com/ee/api/)
- [Amazon Q Business Documentation](https://docs.aws.amazon.com/amazonq/latest/qbusiness-ug/custom-connector.html)
