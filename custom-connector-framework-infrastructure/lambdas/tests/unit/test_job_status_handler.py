from unittest.mock import MagicMock, patch

import pytest

import job_status_handler
from common.storage.ddb.custom_connector_jobs_dao import JobStatus


@pytest.fixture
def mock_jobs_table():
    with patch("job_status_handler.jobs_table") as mock:
        yield mock


@pytest.fixture
def mock_jobs_dao():
    with patch("job_status_handler.jobs_dao") as mock:
        yield mock


@pytest.fixture
def mock_connectors_dao():
    with patch("job_status_handler.connectors_dao") as mock:
        yield mock


def test_process_batch_event_succeeded(mock_jobs_table, mock_jobs_dao, mock_connectors_dao):
    # Arrange
    event_detail = {
        "jobName": "ccj-123456789012",
        "status": "SUCCEEDED",
        "container": {
            "environment": [
                {"name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID", "value": "test-connector"},
                {
                    "name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ARN_PREFIX",
                    "value": "arn:aws:ccf:us-west-2:123456789012",
                },
            ]
        },
    }

    mock_jobs_table.get_item.return_value = {"Item": {"status": JobStatus.RUNNING.value}}

    # Act
    job_status_handler.process_batch_event(event_detail)

    # Assert
    mock_jobs_dao.update_job_status.assert_called_once()
    update_request = mock_jobs_dao.update_job_status.call_args[0][0]
    assert update_request.status == JobStatus.SUCCEEDED
    assert update_request.connector_id == "test-connector"
    assert update_request.job_id == "ccj-123456789012"

    mock_connectors_dao.update_connector_status.assert_called_once()


def test_process_batch_event_failed(mock_jobs_table, mock_jobs_dao, mock_connectors_dao):
    # Arrange
    event_detail = {
        "jobName": "ccj-123456789012",
        "status": "FAILED",
        "container": {
            "environment": [
                {"name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID", "value": "test-connector"},
                {
                    "name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ARN_PREFIX",
                    "value": "arn:aws:ccf:us-west-2:123456789012",
                },
            ]
        },
    }

    mock_jobs_table.get_item.return_value = {"Item": {"status": JobStatus.RUNNING.value}}

    # Act
    job_status_handler.process_batch_event(event_detail)

    # Assert
    mock_jobs_dao.update_job_status.assert_called_once()
    update_request = mock_jobs_dao.update_job_status.call_args[0][0]
    assert update_request.status == JobStatus.FAILED
    assert update_request.connector_id == "test-connector"
    assert update_request.job_id == "ccj-123456789012"

    mock_connectors_dao.update_connector_status.assert_called_once()


def test_process_batch_event_stopped(mock_jobs_table, mock_jobs_dao, mock_connectors_dao):
    # Arrange
    event_detail = {
        "jobName": "ccj-123456789012",
        "status": "FAILED",  # Batch job status is FAILED when cancelled
        "container": {
            "environment": [
                {"name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID", "value": "test-connector"},
                {
                    "name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ARN_PREFIX",
                    "value": "arn:aws:ccf:us-west-2:123456789012",
                },
            ]
        },
    }

    # Job was in STOPPING state before the Batch job failed
    mock_jobs_table.get_item.return_value = {"Item": {"status": JobStatus.STOPPING.value}}

    # Act
    job_status_handler.process_batch_event(event_detail)

    # Assert
    mock_jobs_dao.update_job_status.assert_called_once()
    update_request = mock_jobs_dao.update_job_status.call_args[0][0]
    assert update_request.status == JobStatus.STOPPED  # Should be STOPPED, not FAILED
    assert update_request.connector_id == "test-connector"
    assert update_request.job_id == "ccj-123456789012"

    mock_connectors_dao.update_connector_status.assert_called_once()


def test_process_batch_event_ignore_unsupported_status(mock_jobs_dao, mock_connectors_dao):
    # Arrange
    event_detail = {
        "jobName": "ccj-123456789012",
        "status": "RUNNING",  # Not a terminal status
        "container": {
            "environment": [
                {"name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID", "value": "test-connector"},
                {
                    "name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ARN_PREFIX",
                    "value": "arn:aws:ccf:us-west-2:123456789012",
                },
            ]
        },
    }

    # Act
    job_status_handler.process_batch_event(event_detail)

    # Assert
    mock_jobs_dao.update_job_status.assert_not_called()
    mock_connectors_dao.update_connector_status.assert_not_called()


def test_handler_success():
    # Arrange
    with patch("job_status_handler.process_batch_event") as mock_process:
        event = {"detail": {"jobName": "ccj-123456789012", "status": "SUCCEEDED"}}

        # Create a mock LambdaContext
        mock_context = MagicMock()
        mock_context.function_name = "test-function"
        mock_context.memory_limit_in_mb = 128
        mock_context.invoked_function_arn = "arn:aws:lambda:us-west-2:123456789012:function:test-function"
        mock_context.aws_request_id = "test-request-id"

        # Act
        response = job_status_handler.handler(event, mock_context)

        # Assert
        mock_process.assert_called_once_with(event["detail"])
        assert response["statusCode"] == 200


def test_handler_exception():
    # Arrange
    with patch("job_status_handler.process_batch_event") as mock_process:
        mock_process.side_effect = Exception("Test error")
        event = {"detail": {"jobName": "ccj-123456789012", "status": "SUCCEEDED"}}

        # Create a mock LambdaContext
        mock_context = MagicMock()
        mock_context.function_name = "test-function"
        mock_context.memory_limit_in_mb = 128
        mock_context.invoked_function_arn = "arn:aws:lambda:us-west-2:123456789012:function:test-function"
        mock_context.aws_request_id = "test-request-id"

        # Act/Assert
        with pytest.raises(Exception):
            job_status_handler.handler(event, mock_context)
