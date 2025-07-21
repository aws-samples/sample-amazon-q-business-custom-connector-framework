"""Lambda handler for processing job status changes."""

import boto3
from aws_lambda_powertools.utilities.typing import LambdaContext

from common.env import (CUSTOM_CONNECTOR_JOBS_TABLE_NAME,
                        CUSTOM_CONNECTORS_TABLE_NAME)
from common.observability import LogContext, create_log_context, logger, tracer
from common.storage.ddb.custom_connector_jobs_dao import (
    CustomConnectorJobsDao, JobStatus, UpdateJobStatusRequest)
from common.storage.ddb.custom_connectors_dao import (
    ConnectorStatus, CustomConnectorsDao, UpdateConnectorStatusRequest)
from common.tenant import TenantContext

dynamodb = boto3.resource("dynamodb")

connectors_table = dynamodb.Table(CUSTOM_CONNECTORS_TABLE_NAME)
jobs_table = dynamodb.Table(CUSTOM_CONNECTOR_JOBS_TABLE_NAME)

connectors_dao = CustomConnectorsDao(connectors_table)
jobs_dao = CustomConnectorJobsDao(jobs_table, connectors_dao)


@tracer.capture_method
def process_batch_event(event_detail: dict) -> None:
    """Process a Batch job state change event."""
    batch_job_id = event_detail.get("jobName")  # Same as custom connector job id.
    batch_job_status = event_detail.get("status")

    if not batch_job_id or batch_job_status not in ["SUCCEEDED", "FAILED"]:
        logger.info(
            "Ignoring job with non-actionable status",
            extra={"batch_job_id": batch_job_id, "batch_job_status": batch_job_status},
        )
        return

    # Extract information from environment variables
    container_env = event_detail.get("container", {}).get("environment", [])
    env = {item["name"]: item["value"] for item in container_env}

    connector_id = env.get("CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID")
    connector_arn_prefix = env.get("CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ARN_PREFIX")

    # Create tenant context from ARN prefix
    tenant_context = TenantContext.from_arn_prefix(connector_arn_prefix)

    log_context = create_log_context(
        LogContext(connector_id=connector_id, account_id=tenant_context.account_id, job_id=batch_job_id)
    )

    logger.info("Processing batch job status change", extra={**log_context, "batch_job_status": batch_job_status})

    try:
        # Get the current job status to check if it was in STOPPING state
        job_item = jobs_table.get_item(
            Key={
                "custom_connector_arn_prefix": connector_arn_prefix,
                "job_id": batch_job_id,
            }
        ).get("Item")

        current_status = job_item.get("status") if job_item else None
        logger.debug("Retrieved current job status", extra={**log_context, "current_status": current_status})

        # Map Batch status to our job status
        job_status = None
        if batch_job_status == "SUCCEEDED":
            job_status = JobStatus.SUCCEEDED
        elif batch_job_status == "FAILED":
            # If the job was in STOPPING state, mark it as STOPPED instead of FAILED
            if current_status == JobStatus.STOPPING.value:
                job_status = JobStatus.STOPPED
                logger.info("Job was in STOPPING state, marking as STOPPED", extra=log_context)
            else:
                job_status = JobStatus.FAILED
                logger.info("Job failed, marking as FAILED", extra=log_context)

        if job_status is None:
            logger.warning("Unknown batch job status", extra={**log_context, "batch_job_status": batch_job_status})
            return

        # Update job status
        jobs_dao.update_job_status(
            UpdateJobStatusRequest(
                tenant_context=tenant_context,
                connector_id=connector_id,
                job_id=batch_job_id,
                status=job_status,
                batch_job_id=batch_job_id,
            )
        )
        logger.info("Updated job status successfully", extra={**log_context, "new_status": job_status.value})

        # Make connector available again
        connectors_dao.update_connector_status(
            UpdateConnectorStatusRequest(
                tenant_context=tenant_context, connector_id=connector_id, status=ConnectorStatus.AVAILABLE
            )
        )
        logger.info("Updated connector status to AVAILABLE", extra=log_context)

    except Exception as error:
        logger.warning("Error updating statuses", extra={**log_context, "error": str(error)})
        raise


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event, _context: LambdaContext):
    """Handle Batch job state change events."""
    logger.info("Received EventBridge event", extra={"event_type": "eventbridge", "source": event.get("source")})
    logger.debug("Full event details", extra={"event": event})

    try:
        event_detail = event.get("detail", {})
        process_batch_event(event_detail)
        logger.info("EventBridge event processed successfully")
        return {"statusCode": 200, "body": {"message": "Successfully processed job status change"}}
    except Exception as error:
        logger.exception("Failed to process job status change", extra={"error": str(error)})
        raise
