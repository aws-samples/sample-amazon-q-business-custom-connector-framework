"""Unit tests for the UpdateCustomConnectorActivity class."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.event_handler import Response

from activities.update_custom_connector import (UpdateContainerProperties,
                                                UpdateCustomConnectorActivity,
                                                UpdateCustomConnectorRequest,
                                                UpdateResourceRequirements)
from common.storage.ddb.custom_connectors_dao import (ConnectorStatus,
                                                      DaoConflictError,
                                                      DaoResourceNotFoundError)
from common.tenant import TenantContext


@pytest.fixture
def tenant_context():
    return TenantContext(account_id="123456789012", region="us-east-1")


@pytest.fixture
def mock_dao():
    return MagicMock()


@pytest.fixture
def activity(mock_dao):
    return UpdateCustomConnectorActivity(mock_dao)


def test_update_connector_success(activity, mock_dao, tenant_context):
    # Arrange
    connector_id = "cc-123456789012"
    name = "UpdatedConnector"
    description = "Updated description"
    container_properties = UpdateContainerProperties(
        execution_role_arn="arn:aws:iam::123456789012:role/execution-role",
        image_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/my-image:latest",
        job_role_arn="arn:aws:iam::123456789012:role/job-role",
        resource_requirements=UpdateResourceRequirements(cpu=2, memory=4096),
        timeout=7200,
    )

    request = UpdateCustomConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name=name,
        description=description,
        container_properties=container_properties,
    )

    # Mock the DAO response
    dao_response = MagicMock()
    dao_response.connector_id = connector_id
    dao_response.arn = f"arn:aws:custom-connector:us-east-1:123456789012:{connector_id}"
    dao_response.name = name
    dao_response.created_at = datetime(2023, 1, 1, tzinfo=UTC)
    dao_response.updated_at = datetime(2023, 1, 2, tzinfo=UTC)
    dao_response.description = description
    dao_response.status = ConnectorStatus.AVAILABLE
    mock_dao.update_connector.return_value = dao_response

    # Act
    response = activity.update(request)

    # Assert
    assert isinstance(response, Response)
    assert response.status_code == 200

    response_body = json.loads(response.body)
    assert "connector" in response_body
    assert response_body["connector"]["connector_id"] == connector_id
    assert response_body["connector"]["name"] == name
    assert response_body["connector"]["description"] == description
    assert response_body["connector"]["status"] == ConnectorStatus.AVAILABLE.value

    # Verify DAO was called correctly
    mock_dao.update_connector.assert_called_once()
    dao_request = mock_dao.update_connector.call_args[0][0]
    assert dao_request.tenant_context == tenant_context
    assert dao_request.connector_id == connector_id
    assert dao_request.name == name
    assert dao_request.description == description
    assert dao_request.container_properties is not None


def test_update_connector_not_found(activity, mock_dao, tenant_context):
    # Arrange
    connector_id = "cc-nonexistent"
    request = UpdateCustomConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name="UpdatedName",
    )

    # Mock the DAO to raise a not found error
    mock_dao.update_connector.side_effect = DaoResourceNotFoundError(f"Connector {connector_id} not found")

    # Act
    response = activity.update(request)

    # Assert
    assert isinstance(response, Response)
    assert response.status_code == 404

    response_body = json.loads(response.body)
    assert response_body["errorType"] == "ResourceNotFoundException"
    assert f"Connector {connector_id} not found" in response_body["message"]


def test_update_connector_conflict(activity, mock_dao, tenant_context):
    # Arrange
    connector_id = "cc-123456789012"
    request = UpdateCustomConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name="UpdatedName",
    )

    # Mock the DAO to raise a conflict error
    mock_dao.update_connector.side_effect = DaoConflictError(
        f"Connector '{connector_id}' was modified by another process"
    )

    # Act
    response = activity.update(request)

    # Assert
    assert isinstance(response, Response)
    assert response.status_code == 409

    response_body = json.loads(response.body)
    assert response_body["errorType"] == "ConflictException"
    assert f"Connector '{connector_id}' was modified by another process" in response_body["message"]


def test_update_connector_partial_update(activity, mock_dao, tenant_context):
    # Arrange
    connector_id = "cc-123456789012"
    name = "UpdatedConnector"

    # Only update the name
    request = UpdateCustomConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name=name,
    )

    # Mock the DAO response
    dao_response = MagicMock()
    dao_response.connector_id = connector_id
    dao_response.arn = f"arn:aws:custom-connector:us-east-1:123456789012:{connector_id}"
    dao_response.name = name
    dao_response.created_at = datetime(2023, 1, 1, tzinfo=UTC)
    dao_response.updated_at = datetime(2023, 1, 2, tzinfo=UTC)
    dao_response.description = "Original description"
    dao_response.status = ConnectorStatus.AVAILABLE
    dao_response.version = 2
    mock_dao.update_connector.return_value = dao_response

    # Act
    response = activity.update(request)

    # Assert
    assert isinstance(response, Response)
    assert response.status_code == 200

    response_body = json.loads(response.body)
    assert response_body["connector"]["name"] == name
    assert response_body["connector"]["description"] == "Original description"

    # Verify DAO was called correctly with only name parameter
    mock_dao.update_connector.assert_called_once()
    dao_request = mock_dao.update_connector.call_args[0][0]
    assert dao_request.name == name
    assert dao_request.description is None
    assert dao_request.container_properties is None
