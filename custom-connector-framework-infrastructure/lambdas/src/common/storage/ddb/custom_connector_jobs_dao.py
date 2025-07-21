"""DAO for managing custom connector jobs."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table
from pydantic import BaseModel, Field

from common.storage.ddb.custom_connectors_dao import \
    ConnectorStatus as DaoConnectorStatus
from common.storage.ddb.custom_connectors_dao import CustomConnectorsDao
from common.storage.ddb.custom_connectors_dao import \
    DaoInternalError as ConnectorDaoInternalError
from common.storage.ddb.custom_connectors_dao import \
    DaoResourceNotFoundError as ConnectorDaoNotFoundError
from common.storage.ddb.custom_connectors_dao import (
    GetConnectorRequest, UpdateConnectorStatusRequest)
from common.tenant import TenantContext


class JobStatus(str, Enum):
    """Enumeration of job statuses."""

    STARTED = "STARTED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


class StartJobRequest(BaseModel):
    """Request model for starting a job."""

    tenant_context: TenantContext
    connector_id: str
    environment: list[dict] | None = Field(default_factory=list)


class StartJobResponse(BaseModel):
    """Response model for starting a job."""

    job_id: str
    connector_id: str
    status: JobStatus
    created_at: str


class UpdateJobStatusRequest(BaseModel):
    """Request model for updating job status."""

    tenant_context: TenantContext
    connector_id: str
    job_id: str
    status: JobStatus
    batch_job_id: str | None = None


class ListJobsRequest(BaseModel):
    """Request model for listing jobs."""

    tenant_context: TenantContext
    connector_id: str
    max_results: int = 50
    next_token: str | None = None
    status: JobStatus | None = None


class JobSummary(BaseModel):
    """Summary information for a job."""

    job_id: str
    connector_id: str
    status: JobStatus
    created_at: str


class ListJobsResponse(BaseModel):
    """Response model for listing jobs."""

    jobs: list[JobSummary]
    next_token: str | None = None


class DaoConflictError(Exception):
    """
    Thrown when a resource exists but is in the wrong state.

    (e.g., connector not AVAILABLE or job already in terminal status).
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DaoResourceNotFoundError(Exception):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DaoInternalError(Exception):
    """Exception raised for internal DAO errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConnectorNotFoundError(DaoResourceNotFoundError):
    """Exception for connector not found errors."""

    def __init__(self, connector_id: str):
        super().__init__(f"Connector '{connector_id}' not found")


class JobNotFoundError(DaoResourceNotFoundError):
    """Exception for job not found errors."""

    def __init__(self, job_id: str):
        super().__init__(f"Job with ID '{job_id}' not found")


class ConnectorStateError(DaoConflictError):
    """Exception for connector state conflicts."""

    def __init__(self, connector_id: str, current_state: str):
        super().__init__(f"Connector '{connector_id}' is in state '{current_state}' and is not AVAILABLE")


class JobTerminalStateError(DaoConflictError):
    """Exception for job already in terminal state."""

    def __init__(self, job_id: str, current_status: str):
        super().__init__(f"Job '{job_id}' is already in terminal status '{current_status}'")


class CustomConnectorJobsDao:
    """
    DAO for interacting with the CustomConnectorJobs DynamoDB table.

    Every method first verifies that the given connector exists in the CustomConnectors table.
    - start_job: checks connector exists & AVAILABLE, then marks connector IN_USE and inserts new job.
    - update_job_status: checks connector exists, ensures job not in terminal status,
      updates job status (and batch_job_id), applies TTL if needed, and marks connector AVAILABLE if stopped/failed.
    - list_jobs: checks connector exists, then queries the jobs GSI.

    Raises:
      - DaoResourceNotFoundError if the connector_id (or job_id) isn’t found.
      - DaoConflictError if connector status != AVAILABLE during start_job, or job already terminal.
      - DaoInternalError on any unexpected DynamoDB/DAO failure.

    """

    # TTL window (e.g., 7 days) after a job is marked SUCCEEDED, STOPPED or FAILED
    _TTL_DAYS_AFTER_STOP = 7

    def __init__(self, jobs_table: Table, connectors_dao: CustomConnectorsDao):
        """
        Initialize the CustomConnectorJobsDao.

        Args:
            jobs_table (Table): A boto3 DynamoDB Table resource pointing at CustomConnectorJobs.
            connectors_dao (CustomConnectorsDao): Used to verify connector existence/state and update status.

        """
        self.table = jobs_table
        self.connectors_dao = connectors_dao

    def _verify_connector_exists(self, tenant_context: TenantContext, connector_id: str) -> None:
        """
        Ensure that the connector exists in the CustomConnectors table.

        Raises DaoResourceNotFoundError if missing.
        Raises DaoInternalError on any unexpected error while fetching.
        """
        try:
            get_req = GetConnectorRequest(tenant_context=tenant_context, connector_id=connector_id)
            self.connectors_dao.get_connector(get_req)
        except ConnectorDaoNotFoundError:
            raise ConnectorNotFoundError(connector_id) from None
        except ConnectorDaoInternalError as error:
            raise DaoInternalError(f"Failed to verify connector: {error.message}") from error

    def start_job(self, request: StartJobRequest) -> StartJobResponse:
        """
        Start a new job for a custom connector.

        1. Verify connector exists in CustomConnectors & is AVAILABLE.
           - If not found: raise DaoResourceNotFoundError.
           - If found but status != AVAILABLE: raise DaoConflictError.
        2. Mark connector as IN_USE.
        3. Insert a new job item into DynamoDB with status=STARTED.
           - If insertion fails, roll back connector status to AVAILABLE.

        Raises:
            DaoResourceNotFoundError: if connector_id doesn’t exist.
            DaoConflictError: if connector exists but isn’t in AVAILABLE state.
            DaoInternalError: on any unexpected DynamoDB/DAO failure.

        """
        # Step 1: Verify existence & availability
        try:
            get_req = GetConnectorRequest(tenant_context=request.tenant_context, connector_id=request.connector_id)
            connector_info = self.connectors_dao.get_connector(get_req)
        except ConnectorDaoNotFoundError:
            raise DaoResourceNotFoundError("Connector 'request.connector_id' not found") from None
        except ConnectorDaoInternalError as error:
            raise DaoInternalError(f"Failed to verify connector: {error.message}") from error

        if connector_info.status != DaoConnectorStatus.AVAILABLE:
            raise DaoConflictError(
                f"Connector '{request.connector_id}' is in state '{connector_info.status.value}' and is not AVAILABLE"
            )

        # Step 2: Mark connector as IN_USE
        try:
            update_conn_req = UpdateConnectorStatusRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                status=DaoConnectorStatus.IN_USE,
            )
            self.connectors_dao.update_connector_status(update_conn_req)
        except ConnectorDaoNotFoundError:
            raise DaoResourceNotFoundError(
                f"Connector '{request.connector_id}' not found when marking IN_USE"
            ) from None
        except ConnectorDaoInternalError as error:
            raise DaoInternalError(
                f"Failed to mark connector '{request.connector_id}' IN_USE: {error.message}"
            ) from error

        # Step 3: Insert a new job record
        now_dt = datetime.now(UTC)
        now_iso = now_dt.isoformat()
        job_id = f"ccj-{uuid.uuid4().hex[:12]}"
        arn_prefix = request.tenant_context.get_arn_prefix()

        item = {
            "custom_connector_arn_prefix": arn_prefix,
            "job_id": job_id,
            "connector_id": request.connector_id,
            "status": JobStatus.STARTED.value,
            "environment": request.environment,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        try:
            self.table.put_item(Item=item)
        except ClientError as error:
            # Roll back connector status to AVAILABLE on failure
            try:
                rollback_req = UpdateConnectorStatusRequest(
                    tenant_context=request.tenant_context,
                    connector_id=request.connector_id,
                    status=DaoConnectorStatus.AVAILABLE,
                )
                self.connectors_dao.update_connector_status(rollback_req)
            except Exception:
                pass
            raise DaoInternalError(f"Failed to start job: {error.response['Error']['Message']}") from error

        return StartJobResponse(
            job_id=job_id,
            connector_id=request.connector_id,
            status=JobStatus.STARTED,
            created_at=now_iso,
        )

    def _fetch_job_item(self, tenant_context: TenantContext, job_id: str) -> dict:
        """Fetch job item from DynamoDB."""
        arn_prefix = tenant_context.get_arn_prefix()
        try:
            response = self.table.get_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "job_id": job_id,
                }
            )
        except ClientError as error:
            raise DaoInternalError(f"Failed to fetch job '{job_id}': {error.response['Error']['Message']}") from error

        item = response.get("Item")
        if not item:
            raise DaoResourceNotFoundError(f"Job with ID '{job_id}' not found") from None
        return item

    def _validate_job_status(self, job_id: str, current_status: str) -> None:
        """Validate that job is not already in terminal status."""
        if current_status in (JobStatus.STOPPED.value, JobStatus.FAILED.value):
            raise DaoConflictError(f"Job '{job_id!s}' is already in terminal status '{current_status}'") from None

    def _mark_connector_available_if_terminal(self, request: UpdateJobStatusRequest) -> None:
        """Mark connector as available if job status is terminal."""
        if request.status in (JobStatus.STOPPED, JobStatus.FAILED):
            try:
                update_conn_req = UpdateConnectorStatusRequest(
                    tenant_context=request.tenant_context,
                    connector_id=request.connector_id,
                    status=DaoConnectorStatus.AVAILABLE,
                )
                self.connectors_dao.update_connector_status(update_conn_req)
            except ConnectorDaoNotFoundError:
                pass
            except ConnectorDaoInternalError as error:
                raise DaoInternalError(
                    f"Failed to set connector '{request.connector_id}' AVAILABLE: {error.message}"
                ) from error

    def update_job_status(self, request: UpdateJobStatusRequest) -> None:
        """
        Update the status of a job.

        1. Verify that the connector exists in CustomConnectors.
           - If not found: raise DaoResourceNotFoundError.
        2. Fetch existing job; if status ∈ {STOPPED, FAILED}, raise DaoConflictError.
        3. Update job’s status (and optionally batch_job_id).
           If status ∈ {STOPPED, FAILED}:
             - Set TTL = now + 7 days.
             - Mark connector status back to AVAILABLE.

        Raises:
            DaoResourceNotFoundError: if connector_id (or job_id) is missing.
            DaoConflictError: if job already in terminal status.
            DaoInternalError: if DynamoDB update_item fails unexpectedly.

        """
        # Step 1: Verify existence
        self._verify_connector_exists(request.tenant_context, request.connector_id)

        arn_prefix = request.tenant_context.get_arn_prefix()

        # Step 2: Retrieve current job status
        try:
            response = self.table.get_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "job_id": request.job_id,
                }
            )
        except ClientError as error:
            raise DaoInternalError(
                f"Failed to fetch job '{request.job_id}': {error.response['Error']['Message']}"
            ) from error

        item = response.get("Item")
        if not item:
            raise DaoResourceNotFoundError(f"Job with ID '{request.job_id}' not found") from None

        current_status = item.get("status")
        if current_status in (JobStatus.STOPPED.value, JobStatus.FAILED.value):
            raise DaoConflictError(
                f"Job '{request.job_id!s}' is already in terminal status '{current_status}'"
            ) from None

        # Step 3: Apply update
        now_dt = datetime.now(UTC)
        now_iso = now_dt.isoformat()

        update_expr_parts = ["#status = :status", "updated_at = :updated_at"]
        expr_attr_names = {"#status": "status"}
        expr_attr_values = {
            ":status": request.status.value,
            ":updated_at": now_iso,
        }

        if request.batch_job_id is not None:
            update_expr_parts.append("batch_job_id = :batch_job_id")
            expr_attr_values[":batch_job_id"] = request.batch_job_id

        mark_available = False
        if request.status in (JobStatus.STOPPED, JobStatus.FAILED, JobStatus.SUCCEEDED):
            # Use now_dt + TTL_DAYS for expiration
            expires_at = int((now_dt + timedelta(days=self._TTL_DAYS_AFTER_STOP)).timestamp())
            # ttl is a reserved word, so use an expression attribute name placeholder
            update_expr_parts.append("#ttl = :ttl")
            expr_attr_names["#ttl"] = "ttl"
            # Convert to string to match the expected type
            expr_attr_values[":ttl"] = str(expires_at)
            mark_available = True

        update_expr = "SET " + ", ".join(update_expr_parts)

        try:
            self.table.meta.client.update_item(
                TableName=self.table.name,
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "job_id": request.job_id,
                },
                ConditionExpression="attribute_exists(job_id)",
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
            )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code == "ConditionalCheckFailedException":
                raise DaoResourceNotFoundError(f"Job with ID '{request.job_id}' not found") from error
            raise DaoInternalError(f"Failed to update job status: {error.response['Error']['Message']}") from error

        # Step 4: If terminal, mark connector AVAILABLE
        if mark_available:
            try:
                update_conn_req = UpdateConnectorStatusRequest(
                    tenant_context=request.tenant_context,
                    connector_id=request.connector_id,
                    status=DaoConnectorStatus.AVAILABLE,
                )
                self.connectors_dao.update_connector_status(update_conn_req)
            except ConnectorDaoNotFoundError:
                # If connector got removed after job creation, ignore
                pass
            except ConnectorDaoInternalError as error:
                raise DaoInternalError(
                    f"Failed to set connector '{request.connector_id}' AVAILABLE: {error.message}"
                ) from error

    def list_jobs(self, request: ListJobsRequest) -> ListJobsResponse:
        """
        List jobs for a custom connector.

        1. Verify that the connector exists in CustomConnectors.
           - If not found: raise DaoResourceNotFoundError.
        2. Query the GSI1 index to list jobs for that connector, applying
           optional status filter and pagination.

        Raises:
            DaoResourceNotFoundError: if connector_id doesn’t exist.
            DaoInternalError: if DynamoDB query fails unexpectedly.

        """
        self._verify_connector_exists(request.tenant_context, request.connector_id)

        arn_prefix = request.tenant_context.get_arn_prefix()
        query_params = {
            "IndexName": "GSI1",
            "KeyConditionExpression": Key("custom_connector_arn_prefix").eq(arn_prefix)
            & Key("connector_id").eq(request.connector_id),
            "Limit": request.max_results,
        }

        if request.next_token:
            try:
                query_params["ExclusiveStartKey"] = json.loads(request.next_token)
            except json.JSONDecodeError as error:
                raise DaoInternalError(f"Invalid next_token format: {error!s}") from error

        try:
            response = self.table.query(**query_params)
        except ClientError as error:
            raise DaoInternalError(f"Failed to list jobs: {error.response['Error']['Message']}") from error

        items = response.get("Items", [])
        summaries: list[JobSummary] = []

        for item in items:
            # If a status filter is provided, skip non-matching items
            if request.status and item.get("status") != request.status.value:
                continue

            summaries.append(
                JobSummary(
                    job_id=str(item["job_id"]),
                    connector_id=str(item["connector_id"]),
                    status=JobStatus(item["status"]),
                    created_at=str(item["created_at"]),
                )
            )

        last_key = response.get("LastEvaluatedKey")
        next_token = json.dumps(last_key) if last_key else None

        return ListJobsResponse(jobs=summaries, next_token=next_token)
