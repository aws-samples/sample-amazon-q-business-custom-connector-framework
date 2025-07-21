"""Pytest configuration for the Custom Connector Framework."""

import os
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Filter out deprecation warnings from pytest
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*ast\\..*")
warnings.filterwarnings("ignore", message=".*datetime\\.datetime\\.utcfromtimestamp.*")
warnings.filterwarnings(action="ignore", category=DeprecationWarning, module=r".*datetime")
warnings.filterwarnings(action="ignore", category=DeprecationWarning, module=r".*assertion")
warnings.filterwarnings(action="ignore", category=DeprecationWarning, module=r".*tz")


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for tests."""
    with patch.dict(
        os.environ,
        {
            "CUSTOM_CONNECTORS_TABLE_NAME": "CustomConnectors",
            "CUSTOM_CONNECTOR_JOBS_TABLE_NAME": "CustomConnectorJobs",
            "CUSTOM_CONNECTOR_DOCUMENTS_TABLE_NAME": "CustomConnectorDocuments",
            "AWS_REGION": "us-east-1",
        },
    ):
        yield
