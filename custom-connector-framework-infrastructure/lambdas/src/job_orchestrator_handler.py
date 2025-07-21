"""Lambda handler for orchestrating custom connector jobs."""

from dataclasses import dataclass
from typing import Any

import boto3
from aws_lambda_powertools.utilities.batch import (BatchProcessor, EventType,
                                                   process_partial_response)
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import \
    DynamoDBRecord
from aws_lambda_powertools.utilities.typing import LambdaContext

from common.env import (AWS_BATCH_JOB_QUEUE, CUSTOM_CONNECTOR_API_ENDPOINT,
                        CUSTOM_CONNECTOR_JOBS_TABLE_NAME,
                        CUSTOM_CONNECTORS_TABLE_NAME)
from common.observability import LogContext, create_log_context, logger, tracer
from common.storage.ddb.custom_connector_jobs_dao import (
    CustomConnectorJobsDao, JobStatus, UpdateJobStatusRequest)
from common.storage.ddb.custom_connectors_dao import (
    ConnectorStatus, CustomConnectorsDao, GetConnectorRequest,
    UpdateConnectorStatusRequest)
from common.tenant import TenantContext


@dataclass
class JobStartContext:
    """Context for starting a job."""

    job_id: str
    connector_id: str
    custom_connector_arn_prefix: str
    environment: list
    tenant_context: TenantContext
    log_context: dict[str, Any]


processor = BatchProcessor(event_type=EventType.DynamoDBStreams)
batch_client = boto3.client("batch")
dynamodb = boto3.resource("dynamodb")

connectors_table = dynamodb.Table(CUSTOM_CONNECTORS_TABLE_NAME)
jobs_table = dynamodb.Table(CUSTOM_CONNECTOR_JOBS_TABLE_NAME)

connectors_dao = CustomConnectorsDao(connectors_table)
jobs_dao = CustomConnectorJobsDao(jobs_table, connectors_dao)


@tracer.capture_method
def record_handler(record: DynamoDBRecord):
    """Handle a DynamoDB record."""
    if not record.dynamodb or not record.dynamodb.new_image:
        return

    new_image = record.dynamodb.new_image

    # Extract job details
    job_id = new_image.get("job_id")
    connector_id = new_image.get("connector_id")
    custom_connector_arn_prefix = new_image.get("custom_connector_arn_prefix")
    status = new_image.get("status")
    batch_job_id = new_image.get("batch_job_id")
    environment = new_image.get("environment", [])

    if not all([job_id, connector_id, custom_connector_arn_prefix, status]):
        logger.error(
            "Missing required job information", extra={"job_id": job_id, "connector_id": connector_id, "status": status}
        )
        return

    tenant_context = TenantContext.from_arn_prefix(custom_connector_arn_prefix)

    log_context = create_log_context(
        LogContext(connector_id=connector_id, account_id=tenant_context.account_id, job_id=job_id)
    )

    logger.info(
        "Processing DynamoDB job record", extra={**log_context, "status": status, "event_name": record.event_name}
    )

    # Handle job based on status
    if status == JobStatus.STARTED.value:
        job_context = JobStartContext(
            job_id=job_id,
            connector_id=connector_id,
            custom_connector_arn_prefix=custom_connector_arn_prefix,
            environment=environment,
            tenant_context=tenant_context,
            log_context=log_context,
        )
        handle_job_start(job_context)
    elif status == JobStatus.STOPPING.value:
        handle_job_stop(job_id, connector_id, batch_job_id, tenant_context, log_context)
    else:
        logger.info("Skipping job with non-actionable status", extra={**log_context, "status": status})


@tracer.capture_method
def handle_job_start(
    context_or_job_id, connector_id=None, custom_connector_arn_prefix=None, environment=None, tenant_context=None
):
    """
    Handle starting a job.

    This function supports both the new signature with a JobStartContext object
    and the old signature with individual parameters for backward compatibility with tests.
    """
    # Check if the first argument is a JobStartContext
    if isinstance(context_or_job_id, JobStartContext):
        context = context_or_job_id
    else:
        # Create a context from individual parameters (for backward compatibility)
        job_id = context_or_job_id
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=tenant_context.account_id, job_id=job_id)
        )
        context = JobStartContext(
            job_id=job_id,
            connector_id=connector_id,
            custom_connector_arn_prefix=custom_connector_arn_prefix,
            environment=environment,
            tenant_context=tenant_context,
            log_context=log_context,
        )
    """Handle starting a job."""
    try:
        logger.info("Starting job orchestration", extra=context.log_context)

        # Get connector details
        connector = connectors_dao.get_connector(
            GetConnectorRequest(tenant_context=context.tenant_context, connector_id=context.connector_id)
        )
        logger.info(
            "Retrieved connector details for job", extra={**context.log_context, "connector_name": connector.name}
        )

        # Register job definition
        container_props = connector.container_properties

        environment = [
            # Job context
            {"name": "CUSTOM_CONNECTOR_JOB_ID", "value": context.job_id},
            # Connector context
            {"name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID", "value": context.connector_id},
            {"name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ARN", "value": connector.arn},
            {
                "name": "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ARN_PREFIX",
                "value": context.custom_connector_arn_prefix,
            },
            # API context
            {"name": "AWS_REGION", "value": context.tenant_context.region},
            {"name": "CUSTOM_CONNECTOR_FRAMEWORK_API_ENDPOINT", "value": CUSTOM_CONNECTOR_API_ENDPOINT},
            # Add any custom environment variables from connector configuration
            *context.environment,
        ]

        logger.info(
            "Registering AWS Batch job definition",
            extra={**context.log_context, "image_uri": container_props.image_uri},
        )

        register_response = batch_client.register_job_definition(
            jobDefinitionName=context.job_id,
            type="container",
            containerProperties={
                "image": container_props.image_uri,
                "executionRoleArn": container_props.execution_role_arn,
                "jobRoleArn": container_props.job_role_arn,
                "command": [],
                "environment": environment,
                "resourceRequirements": [
                    {"type": "VCPU", "value": str(container_props.resource_requirements.cpu)},
                    {"type": "MEMORY", "value": str(container_props.resource_requirements.memory)},
                ],
            },
            platformCapabilities=["FARGATE"],
            tags={
                "connector_id": context.connector_id,
                "custom_connector_arn_prefix": context.custom_connector_arn_prefix,
                "job_id": context.job_id,
            },
        )

        logger.info(
            "Registered job definition successfully",
            extra={**context.log_context, "job_definition_arn": register_response["jobDefinitionArn"]},
        )

        submit_response = batch_client.submit_job(
            jobName=context.job_id,
            jobQueue=AWS_BATCH_JOB_QUEUE,
            jobDefinition=register_response["jobDefinitionArn"],
            timeout={"attemptDurationSeconds": container_props.timeout},
        )

        batch_job_id = submit_response["jobId"]
        logger.info(
            "Submitted batch job successfully",
            extra={**context.log_context, "batch_job_id": batch_job_id, "timeout_seconds": container_props.timeout},
        )

        # Update job status to RUNNING with batch job ID
        jobs_dao.update_job_status(
            UpdateJobStatusRequest(
                tenant_context=context.tenant_context,
                connector_id=context.connector_id,
                job_id=context.job_id,
                status=JobStatus.RUNNING,
                batch_job_id=batch_job_id,
            )
        )
        logger.info("Updated job status to RUNNING", extra={**context.log_context, "batch_job_id": batch_job_id})

    except Exception as error:
        logger.exception("Error processing job start", extra={**context.log_context, "error": str(error)})
        if context.tenant_context:
            try:
                jobs_dao.update_job_status(
                    UpdateJobStatusRequest(
                        tenant_context=context.tenant_context,
                        connector_id=context.connector_id,
                        job_id=context.job_id,
                        status=JobStatus.FAILED,
                    )
                )
                logger.info("Updated job status to FAILED after processing error", extra=context.log_context)

                connectors_dao.update_connector_status(
                    UpdateConnectorStatusRequest(
                        tenant_context=context.tenant_context,
                        connector_id=context.connector_id,
                        status=ConnectorStatus.AVAILABLE,
                    )
                )
                logger.info("Made connector available again after processing failure", extra=context.log_context)
            except Exception as update_error:
                logger.exception(
                    "Error updating job status to FAILED",
                    extra={**context.log_context, "update_error": str(update_error)},
                )


@tracer.capture_method
def handle_job_stop(job_id, connector_id, batch_job_id, tenant_context, log_context=None):
    """Handle stopping a job."""
    if log_context is None:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=tenant_context.account_id, job_id=job_id)
        )

    if not batch_job_id:
        logger.error("Missing batch_job_id for job with STOPPING status", extra=log_context)
        return

    try:
        logger.info("Canceling AWS Batch job", extra={**log_context, "batch_job_id": batch_job_id})
        batch_client.cancel_job(jobId=batch_job_id, reason="Job stopped by user via Custom Connector Framework API")
        logger.info(
            "Successfully requested cancellation of AWS Batch job", extra={**log_context, "batch_job_id": batch_job_id}
        )

    except Exception as error:
        logger.exception(
            "Error canceling batch job", extra={**log_context, "batch_job_id": batch_job_id, "error": str(error)}
        )
        try:
            jobs_dao.update_job_status(
                UpdateJobStatusRequest(
                    tenant_context=tenant_context,
                    connector_id=connector_id,
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    batch_job_id=batch_job_id,
                )
            )
            logger.info("Updated job status to FAILED due to cancellation error", extra=log_context)

            connectors_dao.update_connector_status(
                UpdateConnectorStatusRequest(
                    tenant_context=tenant_context, connector_id=connector_id, status=ConnectorStatus.AVAILABLE
                )
            )
            logger.info("Made connector available again after cancellation failure", extra=log_context)
        except Exception as update_error:
            logger.exception(
                "Error updating job status after cancellation failure",
                extra={**log_context, "update_error": str(update_error)},
            )


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event, _context: LambdaContext):
    """Lambda handler function."""
    logger.info(
        "Received DynamoDB Streams event",
        extra={"event_type": "dynamodb_streams", "record_count": len(event.get("Records", []))},
    )
    logger.debug("Full event details", extra={"event": event})

    try:
        result = process_partial_response(
            event=event, record_handler=record_handler, processor=processor, context=_context
        )
        logger.info(
            "DynamoDB Streams event processed successfully", extra={"processed_records": len(event.get("Records", []))}
        )
        return result
    except Exception as error:
        logger.exception("Error processing DynamoDB Streams event", extra={"error": str(error)})
        raise
