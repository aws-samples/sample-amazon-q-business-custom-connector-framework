import json
from unittest.mock import MagicMock

import pytest

from activities.stop_custom_connector_job import (
    StopCustomConnectorJobActivity, StopCustomConnectorJobRequest)
from common.storage.ddb.custom_connector_jobs_dao import (
    DaoConflictError, DaoInternalError, DaoResourceNotFoundError, JobStatus)
from common.tenant import TenantContext


@pytest.fixture
def mock_jobs_dao():
    return MagicMock()


@pytest.fixture
def activity(mock_jobs_dao):
    return StopCustomConnectorJobActivity(mock_jobs_dao)


@pytest.fixture
def tenant_context():
    return TenantContext(account_id="123456789012", region="us-west-2")


def test_stop_job_success(activity, mock_jobs_dao, tenant_context):
    # Arrange
    request = StopCustomConnectorJobRequest(
        tenant_context=tenant_context, connector_id="test-connector", job_id="test-job", batch_job_id="batch-job-123"
    )

    # Act
    response = activity.stop(request)

    # Assert
    mock_jobs_dao.update_job_status.assert_called_once()
    update_request = mock_jobs_dao.update_job_status.call_args[0][0]
    assert update_request.status == JobStatus.STOPPING  # Verify STOPPING status is used
    assert update_request.connector_id == "test-connector"
    assert update_request.job_id == "test-job"
    assert update_request.batch_job_id == "batch-job-123"
    assert response.status_code == 202


def test_stop_job_resource_not_found(activity, mock_jobs_dao, tenant_context):
    # Arrange
    request = StopCustomConnectorJobRequest(
        tenant_context=tenant_context, connector_id="test-connector", job_id="test-job"
    )
    mock_jobs_dao.update_job_status.side_effect = DaoResourceNotFoundError("Resource not found")

    # Act
    response = activity.stop(request)

    # Assert
    assert response.status_code == 404
    body = json.loads(response.body)
    assert "Resource not found" in body["message"]


def test_stop_job_conflict(activity, mock_jobs_dao, tenant_context):
    # Arrange
    request = StopCustomConnectorJobRequest(
        tenant_context=tenant_context, connector_id="test-connector", job_id="test-job"
    )
    mock_jobs_dao.update_job_status.side_effect = DaoConflictError("Job already in terminal state")

    # Act
    response = activity.stop(request)

    # Assert
    assert response.status_code == 409
    body = json.loads(response.body)
    assert "Job already in terminal state" in body["message"]


def test_stop_job_internal_error(activity, mock_jobs_dao, tenant_context):
    # Arrange
    request = StopCustomConnectorJobRequest(
        tenant_context=tenant_context, connector_id="test-connector", job_id="test-job"
    )
    mock_jobs_dao.update_job_status.side_effect = DaoInternalError("Internal error")

    # Act
    response = activity.stop(request)

    # Assert
    assert response.status_code == 500
    body = json.loads(response.body)
    assert "Internal error" in body["message"]
