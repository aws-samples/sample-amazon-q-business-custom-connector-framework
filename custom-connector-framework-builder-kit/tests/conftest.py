"""
Pytest configuration for Custom Connector Framework tests.

This module provides shared fixtures and configuration for all tests,
including handling of optional dependencies like the CCF service.
"""

import boto3
import pytest
from botocore.exceptions import UnknownServiceError


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "ccf_required: mark test as requiring CCF service (may be skipped in CI)")


@pytest.fixture(scope="session")
def ccf_service_available():
    """Check if CCF service is available in the current environment."""
    try:
        # Try to create a CCF client to see if the service is available
        boto3.client("ccf", region_name="us-east-1")
        return True
    except UnknownServiceError:
        return False


def pytest_runtest_setup(item):
    """Skip tests that require CCF service when it's not available."""
    if "ccf_required" in item.keywords:
        try:
            boto3.client("ccf", region_name="us-east-1")
        except UnknownServiceError:
            pytest.skip("CCF service not available - skipping test that requires deployed infrastructure")
