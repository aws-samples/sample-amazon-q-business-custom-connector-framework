"""
Environment variables for the Custom Connector Framework.

This module centralizes all environment variable access for the project.
All environment variables should be accessed through this module.
"""

import os

# API configuration
API_PREFIX = os.environ.get("API_PREFIX", "/api/v1")

# DynamoDB tables
CUSTOM_CONNECTORS_TABLE_NAME = os.environ.get("CUSTOM_CONNECTORS_TABLE_NAME", "CustomConnectors")
CUSTOM_CONNECTOR_JOBS_TABLE_NAME = os.environ.get("CUSTOM_CONNECTOR_JOBS_TABLE_NAME", "CustomConnectorJobs")
CUSTOM_CONNECTOR_DOCUMENTS_TABLE_NAME = os.environ.get(
    "CUSTOM_CONNECTOR_DOCUMENTS_TABLE_NAME", "CustomConnectorDocuments"
)

# Region
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_BATCH_JOB_QUEUE = os.environ.get("AWS_BATCH_JOB_QUEUE")
CUSTOM_CONNECTOR_API_ENDPOINT = os.environ.get("CUSTOM_CONNECTOR_API_ENDPOINT")
