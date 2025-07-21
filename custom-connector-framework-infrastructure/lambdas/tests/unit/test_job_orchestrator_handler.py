from unittest.mock import MagicMock, patch

import pytest
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import \
    DynamoDBRecord

import job_orchestrator_handler
from common.storage.ddb.custom_connector_jobs_dao import JobStatus
from common.tenant import TenantContext


@pytest.fixture
def mock_batch_client():
    with patch("job_orchestrator_handler.batch_client") as mock:
        yield mock


@pytest.fixture
def mock_jobs_dao():
    with patch("job_orchestrator_handler.jobs_dao") as mock:
        yield mock


@pytest.fixture
def mock_connectors_dao():
    with patch("job_orchestrator_handler.connectors_dao") as mock:
        yield mock


def test_handle_job_stop_success(mock_batch_client, mock_jobs_dao, mock_connectors_dao):
    # Arrange
    job_id = "test-job"
    connector_id = "test-connector"
    batch_job_id = "batch-job-123"
    tenant_context = TenantContext(account_id="123456789012", region="us-west-2")

    # Act
    job_orchestrator_handler.handle_job_stop(job_id, connector_id, batch_job_id, tenant_context)

    # Assert
    mock_batch_client.cancel_job.assert_called_once_with(
        jobId=batch_job_id, reason="Job stopped by user via Custom Connector Framework API"
    )
    # No calls to update job status should be made - that happens in job_status_handler
    mock_jobs_dao.update_job_status.assert_not_called()


def test_handle_job_stop_missing_batch_job_id(mock_batch_client):
    # Arrange
    job_id = "test-job"
    connector_id = "test-connector"
    batch_job_id = None
    tenant_context = TenantContext(account_id="123456789012", region="us-west-2")

    # Act
    job_orchestrator_handler.handle_job_stop(job_id, connector_id, batch_job_id, tenant_context)

    # Assert - function should return early without error
    mock_batch_client.cancel_job.assert_not_called()


def test_handle_job_stop_batch_error(mock_batch_client, mock_jobs_dao, mock_connectors_dao):
    # Arrange
    job_id = "test-job"
    connector_id = "test-connector"
    batch_job_id = "batch-job-123"
    tenant_context = TenantContext(account_id="123456789012", region="us-west-2")
    mock_batch_client.cancel_job.side_effect = Exception("Batch error")

    # Act
    job_orchestrator_handler.handle_job_stop(job_id, connector_id, batch_job_id, tenant_context)

    # Assert
    mock_batch_client.cancel_job.assert_called_once()
    mock_jobs_dao.update_job_status.assert_called_once()
    update_request = mock_jobs_dao.update_job_status.call_args[0][0]
    assert update_request.status == JobStatus.FAILED
    assert update_request.connector_id == connector_id
    assert update_request.job_id == job_id
    assert update_request.batch_job_id == batch_job_id
    mock_connectors_dao.update_connector_status.assert_called_once()


def test_record_handler_stopping_status():
    # Arrange
    with patch("job_orchestrator_handler.handle_job_stop") as mock_handle_job_stop:
        record = MagicMock(spec=DynamoDBRecord)
        record.dynamodb.new_image = {
            "job_id": "test-job",
            "connector_id": "test-connector",
            "custom_connector_arn_prefix": "arn:aws:ccf:us-west-2:123456789012",
            "status": JobStatus.STOPPING.value,
            "batch_job_id": "batch-job-123",
        }

        # Act
        job_orchestrator_handler.record_handler(record)

        # Assert
        # Check that handle_job_stop was called with the right parameters (ignoring log_context)
        assert mock_handle_job_stop.call_count == 1
        args, kwargs = mock_handle_job_stop.call_args
        assert args[0] == "test-job"
        assert args[1] == "test-connector"
        assert args[2] == "batch-job-123"
        assert isinstance(args[3], TenantContext)
        assert args[3].account_id == "123456789012"
        assert args[3].region == "us-west-2"


def test_record_handler_started_status():
    # Arrange
    with patch("job_orchestrator_handler.handle_job_start") as mock_handle_job_start:
        record = MagicMock(spec=DynamoDBRecord)
        record.dynamodb.new_image = {
            "job_id": "test-job",
            "connector_id": "test-connector",
            "custom_connector_arn_prefix": "arn:aws:ccf:us-west-2:123456789012",
            "status": JobStatus.STARTED.value,
            "environment": [],
        }

        # Act
        job_orchestrator_handler.record_handler(record)

        # Assert
        # Check that handle_job_start was called with a JobStartContext
        assert mock_handle_job_start.call_count == 1
        args, kwargs = mock_handle_job_start.call_args
        assert len(args) == 1
        assert isinstance(args[0], job_orchestrator_handler.JobStartContext)
        assert args[0].job_id == "test-job"
        assert args[0].connector_id == "test-connector"
        assert args[0].custom_connector_arn_prefix == "arn:aws:ccf:us-west-2:123456789012"
        assert args[0].environment == []
        assert isinstance(args[0].tenant_context, TenantContext)
        assert args[0].tenant_context.account_id == "123456789012"
        assert args[0].tenant_context.region == "us-west-2"


def test_record_handler_other_status():
    # Arrange
    with patch("job_orchestrator_handler.handle_job_start") as mock_handle_job_start:
        with patch("job_orchestrator_handler.handle_job_stop") as mock_handle_job_stop:
            record = MagicMock(spec=DynamoDBRecord)
            record.dynamodb.new_image = {
                "job_id": "test-job",
                "connector_id": "test-connector",
                "custom_connector_arn_prefix": "arn:aws:ccf:us-west-2:123456789012",
                "status": JobStatus.RUNNING.value,
            }

            # Act
            job_orchestrator_handler.record_handler(record)

            # Assert
            mock_handle_job_start.assert_not_called()
            mock_handle_job_stop.assert_not_called()


def test_handle_job_start_with_timeout(mock_batch_client, mock_jobs_dao, mock_connectors_dao):
    # Arrange
    job_id = "test-job"
    connector_id = "test-connector"
    custom_connector_arn_prefix = "arn:aws:ccf:us-west-2:123456789012"
    environment = []
    tenant_context = TenantContext(account_id="123456789012", region="us-west-2")

    # Create a JobStartContext
    log_context = job_orchestrator_handler.create_log_context(
        job_orchestrator_handler.LogContext(
            connector_id=connector_id, account_id=tenant_context.account_id, job_id=job_id
        )
    )

    job_context = job_orchestrator_handler.JobStartContext(
        job_id=job_id,
        connector_id=connector_id,
        custom_connector_arn_prefix=custom_connector_arn_prefix,
        environment=environment,
        tenant_context=tenant_context,
        log_context=log_context,
    )

    # Mock connector with timeout
    connector = MagicMock()
    connector.container_properties.timeout = 7200  # 2 hours
    connector.container_properties.image_uri = "test-image"
    connector.container_properties.execution_role_arn = "test-exec-role"
    connector.container_properties.job_role_arn = "test-job-role"
    connector.container_properties.resource_requirements.cpu = 1024
    connector.container_properties.resource_requirements.memory = 2048
    connector.arn = "test-arn"
    mock_connectors_dao.get_connector.return_value = connector

    # Mock batch client responses
    mock_batch_client.register_job_definition.return_value = {"jobDefinitionArn": "test-job-def-arn"}
    mock_batch_client.submit_job.return_value = {"jobId": "batch-job-123"}

    # Act
    job_orchestrator_handler.handle_job_start(job_context)

    # Assert
    mock_batch_client.submit_job.assert_called_once()
    # Verify timeout parameter was passed correctly
    call_args = mock_batch_client.submit_job.call_args[1]
    assert "timeout" in call_args
    assert call_args["timeout"]["attemptDurationSeconds"] == 7200
