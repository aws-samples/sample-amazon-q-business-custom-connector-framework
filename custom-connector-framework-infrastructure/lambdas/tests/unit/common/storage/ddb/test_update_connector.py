"""Unit tests for the update_connector method in CustomConnectorsDao."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table

from common.storage.ddb.custom_connectors_dao import (
    ConnectorStatus, CustomConnectorsDao, DaoConflictError,
    DaoResourceNotFoundError, UpdateConnectorRequest,
    UpdateContainerProperties, UpdateResourceRequirements)
from common.tenant import TenantContext


@pytest.fixture
def tenant_context():
    return TenantContext(account_id="123456789012", region="us-east-1")


@pytest.fixture
def mock_table():
    return MagicMock(spec=Table)


@pytest.fixture
def dao(mock_table):
    return CustomConnectorsDao(mock_table)


def test_update_connector_success(dao, mock_table, tenant_context):
    # Arrange
    connector_id = "cc-123456789012"
    name = "Updated Connector"
    description = "Updated description"
    container_properties = UpdateContainerProperties(
        execution_role_arn="arn:aws:iam::123456789012:role/execution-role",
        image_uri="123456789012.dkr.ecr.us-east-1.amazonaws.com/my-image:latest",
        job_role_arn="arn:aws:iam::123456789012:role/job-role",
        resource_requirements=UpdateResourceRequirements(cpu=2, memory=4096),
        timeout=7200,
    )

    request = UpdateConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name=name,
        description=description,
        container_properties=container_properties,
    )

    # Mock the get_item response
    created_at = datetime(2023, 1, 1, tzinfo=UTC).isoformat()
    updated_at = datetime(2023, 1, 2, tzinfo=UTC).isoformat()
    mock_table.get_item.return_value = {
        "Item": {
            "custom_connector_arn_prefix": "arn:aws:ccf:us-east-1:123456789012",
            "connector_id": connector_id,
            "arn": f"arn:aws:ccf:us-east-1:123456789012:custom-connector/{connector_id}",
            "name": "Original Name",
            "description": "Original description",
            "container_properties": {
                "execution_role_arn": "arn:aws:iam::123456789012:role/original-execution-role",
                "image_uri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/original-image:latest",
                "job_role_arn": "arn:aws:iam::123456789012:role/original-job-role",
                "resource_requirements": {"cpu": 1, "memory": 2048},
                "timeout": 3600,
            },
            "status": ConnectorStatus.AVAILABLE.value,
            "created_at": created_at,
            "updated_at": updated_at,
            "version": 1,
        }
    }

    # Act
    response = dao.update_connector(request)

    # Assert
    assert response.connector_id == connector_id
    assert response.name == name
    assert response.description == description
    assert response.status == ConnectorStatus.AVAILABLE
    # version field is not in the response model

    # Verify put_item was called with the correct parameters
    mock_table.put_item.assert_called_once()
    put_item_args = mock_table.put_item.call_args[1]
    assert "Item" in put_item_args
    assert put_item_args["Item"]["name"] == name
    assert put_item_args["Item"]["description"] == description
    assert put_item_args["Item"]["container_properties"] == container_properties.model_dump()
    assert put_item_args["Item"]["version"] == 2
    assert "ConditionExpression" in put_item_args
    assert put_item_args["ConditionExpression"] == "version = :current_version"
    assert put_item_args["ExpressionAttributeValues"] == {":current_version": 1}


def test_update_connector_not_found(dao, mock_table, tenant_context):
    # Arrange
    connector_id = "cc-nonexistent"
    request = UpdateConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name="Updated Name",
    )

    # Mock the get_item response for a non-existent connector
    mock_table.get_item.return_value = {"Item": None}

    # Act & Assert
    with pytest.raises(DaoResourceNotFoundError) as excinfo:
        dao.update_connector(request)

    assert f"Connector {connector_id} not found" in str(excinfo.value)


def test_update_connector_optimistic_locking_conflict(dao, mock_table, tenant_context):
    # Arrange
    connector_id = "cc-123456789012"
    request = UpdateConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name="Updated Name",
    )

    # Mock the get_item response
    created_at = datetime(2023, 1, 1, tzinfo=UTC).isoformat()
    updated_at = datetime(2023, 1, 2, tzinfo=UTC).isoformat()
    mock_table.get_item.return_value = {
        "Item": {
            "custom_connector_arn_prefix": "arn:aws:ccf:us-east-1:123456789012",
            "connector_id": connector_id,
            "arn": f"arn:aws:ccf:us-east-1:123456789012:custom-connector/{connector_id}",
            "name": "Original Name",
            "description": "Original description",
            "container_properties": {
                "execution_role_arn": "arn:aws:iam::123456789012:role/original-execution-role",
                "image_uri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/original-image:latest",
                "job_role_arn": "arn:aws:iam::123456789012:role/original-job-role",
                "resource_requirements": {"cpu": 1, "memory": 2048},
                "timeout": 3600,
            },
            "status": ConnectorStatus.AVAILABLE.value,
            "created_at": created_at,
            "updated_at": updated_at,
            "version": 1,
        }
    }

    # Mock put_item to raise a ConditionalCheckFailedException
    error_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}}
    mock_table.put_item.side_effect = ClientError(error_response, "PutItem")

    # Act & Assert
    with pytest.raises(DaoConflictError) as excinfo:
        dao.update_connector(request)

    assert f"Connector '{connector_id}' was modified by another process" in str(excinfo.value)


def test_update_connector_partial_update(dao, mock_table, tenant_context):
    # Arrange
    connector_id = "cc-123456789012"
    name = "Updated Name"

    # Only update the name
    request = UpdateConnectorRequest(
        tenant_context=tenant_context,
        connector_id=connector_id,
        name=name,
    )

    # Mock the get_item response
    created_at = datetime(2023, 1, 1, tzinfo=UTC).isoformat()
    updated_at = datetime(2023, 1, 2, tzinfo=UTC).isoformat()
    original_description = "Original description"
    original_container_properties = {
        "execution_role_arn": "arn:aws:iam::123456789012:role/original-execution-role",
        "image_uri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/original-image:latest",
        "job_role_arn": "arn:aws:iam::123456789012:role/original-job-role",
        "resource_requirements": {"cpu": 1, "memory": 2048},
        "timeout": 3600,
    }

    mock_table.get_item.return_value = {
        "Item": {
            "custom_connector_arn_prefix": "arn:aws:ccf:us-east-1:123456789012",
            "connector_id": connector_id,
            "arn": f"arn:aws:ccf:us-east-1:123456789012:custom-connector/{connector_id}",
            "name": "Original Name",
            "description": original_description,
            "container_properties": original_container_properties,
            "status": ConnectorStatus.AVAILABLE.value,
            "created_at": created_at,
            "updated_at": updated_at,
            "version": 1,
        }
    }

    # Act
    response = dao.update_connector(request)

    # Assert
    assert response.connector_id == connector_id
    assert response.name == name
    assert response.description == original_description
    assert response.status == ConnectorStatus.AVAILABLE
    # version field is not in the response model

    # Verify put_item was called with the correct parameters
    mock_table.put_item.assert_called_once()
    put_item_args = mock_table.put_item.call_args[1]
    assert put_item_args["Item"]["name"] == name
    assert put_item_args["Item"]["description"] == original_description
    assert put_item_args["Item"]["container_properties"] == original_container_properties
    assert put_item_args["Item"]["version"] == 2
