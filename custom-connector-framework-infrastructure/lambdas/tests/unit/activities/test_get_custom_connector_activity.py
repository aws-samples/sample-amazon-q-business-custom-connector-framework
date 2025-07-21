"""Unit tests for the GetCustomConnectorActivity class."""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.event_handler import Response

from activities.get_custom_connector import (ConnectorStatus,
                                             GetCustomConnectorActivity,
                                             GetCustomConnectorRequest)
from common.storage.ddb.custom_connectors_dao import (ContainerProperties,
                                                      CustomConnectorsDao,
                                                      DaoResourceNotFoundError,
                                                      GetConnectorResponse,
                                                      ResourceRequirements)
from common.tenant import TenantContext


@pytest.fixture
def mock_dao():
    """Create a mock DAO for testing."""
    return MagicMock(spec=CustomConnectorsDao)


@pytest.fixture
def activity(mock_dao):
    """Create an activity instance with a mock DAO."""
    return GetCustomConnectorActivity(mock_dao)


@pytest.fixture
def tenant_context():
    """Create a tenant context for testing."""
    return TenantContext(account_id="123456789012", region="us-east-1")


@pytest.fixture
def connector_id():
    """Create a connector ID for testing."""
    return "cc-abcdef123456"


@pytest.fixture
def container_properties():
    """Create container properties for testing."""
    return ContainerProperties(
        execution_role_arn="arn:aws:iam::123456789012:role/execution-role",
        image_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/test-image:latest",
        job_role_arn="arn:aws:iam::123456789012:role/job-role",
        resource_requirements=ResourceRequirements(cpu=1, memory=2048),
        timeout=3600,
    )


def test_fetch_success(activity, mock_dao, tenant_context, connector_id, container_properties):
    """Test successful fetch of a connector."""
    # Arrange
    request = GetCustomConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
    )

    created_at = datetime.now()
    updated_at = datetime.now()

    dao_response = GetConnectorResponse(
        connector_id=connector_id,
        arn=f"arn:aws:ccf:us-east-1:123456789012:custom-connector/{connector_id}",
        name="test-connector",
        created_at=created_at,
        updated_at=updated_at,
        description="Test connector",
        status=ConnectorStatus.AVAILABLE,
        container_properties=container_properties,
        checkpoint=None,
        version=1,
    )

    mock_dao.get_connector.return_value = dao_response

    # Act
    response = activity.fetch(request)

    # Assert
    mock_dao.get_connector.assert_called_once()
    assert isinstance(response, Response)
    assert response.status_code == 200

    body = json.loads(response.body)
    assert "connector" in body

    connector = body["connector"]
    assert connector["connector_id"] == connector_id
    assert connector["name"] == "test-connector"
    assert connector["description"] == "Test connector"
    assert connector["status"] == "AVAILABLE"

    # Verify container_properties is included in the response
    assert "container_properties" in connector
    assert connector["container_properties"]["execution_role_arn"] == container_properties.execution_role_arn
    assert connector["container_properties"]["image_uri"] == container_properties.image_uri
    assert connector["container_properties"]["job_role_arn"] == container_properties.job_role_arn
    assert float(connector["container_properties"]["resource_requirements"]["cpu"]) == float(
        container_properties.resource_requirements.cpu
    )
    assert (
        connector["container_properties"]["resource_requirements"]["memory"]
        == container_properties.resource_requirements.memory
    )
    assert connector["container_properties"]["timeout"] == container_properties.timeout


def test_fetch_not_found(activity, mock_dao, tenant_context, connector_id):
    """Test fetch when connector is not found."""
    # Arrange
    request = GetCustomConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
    )

    error_message = f"Connector {connector_id} not found"
    mock_dao.get_connector.side_effect = DaoResourceNotFoundError(error_message)

    # Act
    response = activity.fetch(request)

    # Assert
    mock_dao.get_connector.assert_called_once()
    assert isinstance(response, Response)
    assert response.status_code == 404

    body = json.loads(response.body)
    assert "message" in body
    assert error_message in body["message"]
    assert "errorType" in body
    assert body["errorType"] == "ResourceNotFoundException"


def test_fetch_unexpected_error(activity, mock_dao, tenant_context, connector_id):
    """Test fetch when an unexpected error occurs."""
    # Arrange
    request = GetCustomConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
    )

    error_message = "Unexpected error"
    mock_dao.get_connector.side_effect = Exception(error_message)

    # Act
    response = activity.fetch(request)

    # Assert
    mock_dao.get_connector.assert_called_once()
    assert isinstance(response, Response)
    assert response.status_code == 500

    body = json.loads(response.body)
    assert "message" in body
    assert error_message in body["message"]
    assert "errorType" in body
    assert body["errorType"] == "InternalServerError"
