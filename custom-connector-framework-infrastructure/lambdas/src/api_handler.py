"""
API Gateway handler for the Custom Connector Framework.

This module implements the Lambda function that handles API Gateway requests
for the Custom Connector Framework REST API. It defines routes for all API
operations and delegates to the appropriate activity classes for business logic.

The handler uses AWS Lambda Powertools for standardized logging, metrics,
and tracing, as well as API Gateway integration.
"""

import json
from typing import Any

import boto3
from aws_lambda_powertools.event_handler import (APIGatewayRestResolver,
                                                 Response)
from aws_lambda_powertools.utilities.typing import LambdaContext

from activities.batch_delete_custom_connector_documents import (
    BatchDeleteCustomConnectorDocumentsActivity,
    BatchDeleteCustomConnectorDocumentsRequest)
from activities.batch_put_custom_connector_documents import (
    BatchPutCustomConnectorDocumentsActivity,
    BatchPutCustomConnectorDocumentsRequest)
from activities.create_custom_connector import (ContainerProperties,
                                                CreateCustomConnectorActivity,
                                                CreateCustomConnectorRequest)
from activities.delete_custom_connector import (DeleteCustomConnectorActivity,
                                                DeleteCustomConnectorRequest)
from activities.delete_custom_connector_checkpoint import (
    DeleteCustomConnectorCheckpointActivity,
    DeleteCustomConnectorCheckpointRequest)
from activities.get_custom_connector import (GetCustomConnectorActivity,
                                             GetCustomConnectorRequest)
from activities.get_custom_connector_checkpoint import (
    GetCustomConnectorCheckpointActivity, GetCustomConnectorCheckpointRequest)
from activities.list_custom_connector_documents import (
    ListCustomConnectorDocumentsActivity, ListCustomConnectorDocumentsRequest)
from activities.list_custom_connector_jobs import \
    ListCustomConnectorJobsActivity
from activities.list_custom_connector_jobs import \
    ListCustomConnectorJobsRequest as ListJobsActivityRequest
from activities.list_custom_connectors import (ListCustomConnectorsActivity,
                                               ListCustomConnectorsRequest)
from activities.put_custom_connector_checkpoint import (
    PutCustomConnectorCheckpointActivity, PutCustomConnectorCheckpointRequest)
from activities.start_custom_connector_job import (
    EnvironmentVariable, StartCustomConnectorJobActivity,
    StartCustomConnectorJobRequest)
from activities.stop_custom_connector_job import (
    StopCustomConnectorJobActivity, StopCustomConnectorJobRequest)
from activities.update_custom_connector import (UpdateContainerProperties,
                                                UpdateCustomConnectorActivity,
                                                UpdateCustomConnectorRequest)
from common.env import (CUSTOM_CONNECTOR_DOCUMENTS_TABLE_NAME,
                        CUSTOM_CONNECTOR_JOBS_TABLE_NAME,
                        CUSTOM_CONNECTORS_TABLE_NAME)
from common.observability import LogContext, create_log_context, logger
from common.response import create_error_response
from common.storage.ddb.custom_connector_documents_dao import \
    CustomConnectorDocumentsDao
from common.storage.ddb.custom_connector_jobs_dao import CustomConnectorJobsDao
from common.storage.ddb.custom_connectors_dao import CustomConnectorsDao
from common.tenant import TenantContext, extract_tenant_context

app = APIGatewayRestResolver()
dynamodb = boto3.resource("dynamodb")

connectors_table = dynamodb.Table(CUSTOM_CONNECTORS_TABLE_NAME)
jobs_table = dynamodb.Table(CUSTOM_CONNECTOR_JOBS_TABLE_NAME)
documents_table = dynamodb.Table(CUSTOM_CONNECTOR_DOCUMENTS_TABLE_NAME)

connectors_dao = CustomConnectorsDao(connectors_table)
jobs_dao = CustomConnectorJobsDao(jobs_table, connectors_dao)
documents_dao = CustomConnectorDocumentsDao(documents_table, connectors_dao)

create_connector_activity = CreateCustomConnectorActivity(connectors_dao)
get_connector_activity = GetCustomConnectorActivity(connectors_dao)
list_connectors_activity = ListCustomConnectorsActivity(connectors_dao)
delete_connector_activity = DeleteCustomConnectorActivity(connectors_dao)
update_connector_activity = UpdateCustomConnectorActivity(connectors_dao)

start_job_activity = StartCustomConnectorJobActivity(jobs_dao)
stop_job_activity = StopCustomConnectorJobActivity(jobs_dao)
list_jobs_activity = ListCustomConnectorJobsActivity(jobs_dao)

put_checkpoint_activity = PutCustomConnectorCheckpointActivity(connectors_dao)
get_checkpoint_activity = GetCustomConnectorCheckpointActivity(connectors_dao)
delete_checkpoint_activity = DeleteCustomConnectorCheckpointActivity(connectors_dao)

batch_put_docs_activity = BatchPutCustomConnectorDocumentsActivity(documents_dao)
batch_delete_docs_activity = BatchDeleteCustomConnectorDocumentsActivity(documents_dao)
list_docs_activity = ListCustomConnectorDocumentsActivity(documents_dao)


@app.post("/api/v1/custom-connectors")
def create_custom_connector() -> Response:
    """Create a new custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        body = json.loads(app.current_event.body or "{}")

        log_context = create_log_context(LogContext(account_id=tenant_context.account_id))
        logger.info("Creating custom connector", extra=log_context)
        logger.debug("Create connector request body", extra={**log_context, "request_body": body})

        activity_req = CreateCustomConnectorRequest(
            tenant_context=tenant_context,
            name=body["name"],
            description=body.get("description"),
            container_properties=ContainerProperties(**body["container_properties"]),
        )

        response = create_connector_activity.create(activity_req)

        logger.info("Custom connector created successfully", extra={**log_context, "status_code": response.status_code})
        return response

    except Exception as error:
        log_context = create_log_context(LogContext(account_id=getattr(tenant_context, "account_id", None)))
        logger.exception("Error creating custom connector", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.get("/api/v1/custom-connectors/<connector_id>")
def get_custom_connector(connector_id: str) -> Response:
    """Get a custom connector by ID."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info("Getting custom connector", extra=log_context)

        activity_req = GetCustomConnectorRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
        )

        response = get_connector_activity.fetch(activity_req)

        logger.info(
            "Custom connector retrieved successfully", extra={**log_context, "status_code": response.status_code}
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error getting custom connector", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.get("/api/v1/custom-connectors")
def list_custom_connectors() -> Response:
    """List all custom connectors."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        query_string = app.current_event.query_string_parameters or {}

        log_context = create_log_context(LogContext(account_id=tenant_context.account_id))
        logger.info(
            "Listing custom connectors", extra={**log_context, "max_results": query_string.get("max_results", 50)}
        )

        activity_req = ListCustomConnectorsRequest(
            tenant_context=tenant_context,
            max_results=int(query_string.get("max_results", 50)),
            next_token=query_string.get("next_token"),
        )

        response = list_connectors_activity.list(activity_req)

        logger.info("Custom connectors listed successfully", extra={**log_context, "status_code": response.status_code})
        return response

    except Exception as error:
        log_context = create_log_context(LogContext(account_id=getattr(tenant_context, "account_id", None)))
        logger.exception("Error listing custom connectors", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.delete("/api/v1/custom-connectors/<connector_id>")
def delete_custom_connector(connector_id: str) -> Response:
    """Delete a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info("Deleting custom connector", extra=log_context)

        activity_req = DeleteCustomConnectorRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
        )

        response = delete_connector_activity.delete(activity_req)

        logger.info("Custom connector deleted successfully", extra={**log_context, "status_code": response.status_code})
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error deleting custom connector", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.put("/api/v1/custom-connectors/<connector_id>")
def update_custom_connector(connector_id: str) -> Response:
    """Update a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        body = json.loads(app.current_event.body or "{}")

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info("Updating custom connector", extra=log_context)
        logger.debug("Update connector request body", extra={**log_context, "request_body": body})

        # Extract fields from the request body
        name = body.get("name")
        description = body.get("description")
        container_properties = body.get("container_properties")

        # Create the activity request
        activity_req = UpdateCustomConnectorRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            name=name,
            description=description,
            container_properties=UpdateContainerProperties(**container_properties) if container_properties else None,
        )

        response = update_connector_activity.update(activity_req)

        logger.info("Custom connector updated successfully", extra={**log_context, "status_code": response.status_code})
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error updating custom connector", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.post("/api/v1/custom-connectors/<connector_id>/jobs")
def start_custom_connector_job(connector_id: str) -> Response:
    """Start a custom connector job."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        body = json.loads(app.current_event.body or "{}")

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info("Starting custom connector job", extra=log_context)
        logger.debug("Start job request body", extra={**log_context, "request_body": body})

        activity_req = StartCustomConnectorJobRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            environment=[EnvironmentVariable(**env) for env in body.get("environment", [])],
        )

        response = start_job_activity.start(activity_req)

        logger.info(
            "Custom connector job started successfully", extra={**log_context, "status_code": response.status_code}
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error starting custom connector job", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.post("/api/v1/custom-connectors/<connector_id>/jobs/<job_id>/stop")
def stop_custom_connector_job(connector_id: str, job_id: str) -> Response:
    """Stop a custom connector job."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)

        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=tenant_context.account_id, job_id=job_id)
        )
        logger.info("Stopping custom connector job", extra=log_context)

        activity_req = StopCustomConnectorJobRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            job_id=job_id,
        )

        response = stop_job_activity.stop(activity_req)

        logger.info(
            "Custom connector job stopped successfully", extra={**log_context, "status_code": response.status_code}
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None), job_id=job_id)
        )
        logger.exception("Error stopping custom connector job", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.get("/api/v1/custom-connectors/<connector_id>/jobs")
def list_custom_connector_jobs(connector_id: str) -> Response:
    """List jobs for a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        query_string = app.current_event.query_string_parameters or {}
        status_str = query_string.get("status")
        status = status_str and query_string.get("status")

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info(
            "Listing custom connector jobs",
            extra={**log_context, "status_filter": status, "max_results": query_string.get("max_results", 50)},
        )

        activity_req = ListJobsActivityRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            max_results=int(query_string.get("max_results", 50)),
            next_token=query_string.get("next_token"),
            status=(status and status.strip()) or None,
        )

        response = list_jobs_activity.list(activity_req)

        logger.info(
            "Custom connector jobs listed successfully", extra={**log_context, "status_code": response.status_code}
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error listing custom connector jobs", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.put("/api/v1/custom-connectors/<connector_id>/checkpoint")
def put_custom_connector_checkpoint(connector_id: str) -> Response:
    """Put a checkpoint for a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        body = json.loads(app.current_event.body or "{}")

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info("Putting custom connector checkpoint", extra=log_context)
        logger.debug("Put checkpoint request body", extra={**log_context, "request_body": body})

        activity_req = PutCustomConnectorCheckpointRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            checkpoint_data=body["checkpoint_data"],
        )

        response = put_checkpoint_activity.put(activity_req)

        logger.info(
            "Custom connector checkpoint put successfully", extra={**log_context, "status_code": response.status_code}
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error putting custom connector checkpoint", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.get("/api/v1/custom-connectors/<connector_id>/checkpoint")
def get_custom_connector_checkpoint(connector_id: str) -> Response:
    """Get a checkpoint for a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info("Getting custom connector checkpoint", extra=log_context)

        activity_req = GetCustomConnectorCheckpointRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
        )

        response = get_checkpoint_activity.fetch(activity_req)

        logger.info(
            "Custom connector checkpoint retrieved successfully",
            extra={**log_context, "status_code": response.status_code},
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error getting custom connector checkpoint", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.delete("/api/v1/custom-connectors/<connector_id>/checkpoint")
def delete_custom_connector_checkpoint(connector_id: str) -> Response:
    """Delete a checkpoint for a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info("Deleting custom connector checkpoint", extra=log_context)

        activity_req = DeleteCustomConnectorCheckpointRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
        )

        response = delete_checkpoint_activity.delete(activity_req)

        logger.info(
            "Custom connector checkpoint deleted successfully",
            extra={**log_context, "status_code": response.status_code},
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error deleting custom connector checkpoint", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.post("/api/v1/custom-connectors/<connector_id>/documents")
def batch_put_custom_connector_documents(connector_id: str) -> Response:
    """Batch put documents for a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        body = json.loads(app.current_event.body or "{}")

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info(
            "Batch putting custom connector documents",
            extra={**log_context, "document_count": len(body.get("documents", []))},
        )

        activity_req = BatchPutCustomConnectorDocumentsRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            documents=body["documents"],
        )

        response = batch_put_docs_activity.put(activity_req)

        logger.info(
            "Custom connector documents batch put successfully",
            extra={**log_context, "status_code": response.status_code},
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error batch putting custom connector documents", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.delete("/api/v1/custom-connectors/<connector_id>/documents")
def batch_delete_custom_connector_documents(connector_id: str) -> Response:
    """Batch delete documents for a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        body = json.loads(app.current_event.body or "{}")

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info(
            "Batch deleting custom connector documents",
            extra={**log_context, "document_id_count": len(body.get("document_ids", []))},
        )

        activity_req = BatchDeleteCustomConnectorDocumentsRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            document_ids=body["document_ids"],
        )

        response = batch_delete_docs_activity.delete(activity_req)

        logger.info(
            "Custom connector documents batch deleted successfully",
            extra={**log_context, "status_code": response.status_code},
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error batch deleting custom connector documents", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@app.get("/api/v1/custom-connectors/<connector_id>/documents")
def list_custom_connector_documents(connector_id: str) -> Response:
    """List documents for a custom connector."""
    try:
        tenant_context: TenantContext = extract_tenant_context(app.current_event.raw_event)
        query_string = app.current_event.query_string_parameters or {}

        log_context = create_log_context(LogContext(connector_id=connector_id, account_id=tenant_context.account_id))
        logger.info(
            "Listing custom connector documents",
            extra={**log_context, "max_results": query_string.get("max_results", 50)},
        )

        activity_req = ListCustomConnectorDocumentsRequest(
            tenant_context=tenant_context,
            connector_id=connector_id,
            max_results=int(query_string.get("max_results", 50)),
            next_token=query_string.get("next_token"),
        )

        response = list_docs_activity.list(activity_req)

        logger.info(
            "Custom connector documents listed successfully", extra={**log_context, "status_code": response.status_code}
        )
        return response

    except Exception as error:
        log_context = create_log_context(
            LogContext(connector_id=connector_id, account_id=getattr(tenant_context, "account_id", None))
        )
        logger.exception("Error listing custom connector documents", extra={**log_context, "error": str(error)})
        return create_error_response(error)


@logger.inject_lambda_context
def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Lambda handler function."""
    logger.info(
        "Received API Gateway event",
        extra={"event_type": "api_gateway", "http_method": event.get("httpMethod"), "resource": event.get("resource")},
    )
    logger.debug("Full event details", extra={"event": event})

    try:
        response = app.resolve(event, context)
        logger.info("API Gateway request processed successfully", extra={"status_code": response.get("statusCode")})
        return response
    except Exception as error:
        logger.exception("Error processing API Gateway request", extra={"error": str(error)})
        raise
