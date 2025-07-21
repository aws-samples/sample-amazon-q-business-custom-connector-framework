"""Activity for starting custom connector jobs."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import (ConflictError, InternalServerError,
                               ResourceNotFoundError)
from common.observability import LogContext, create_log_context, logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connector_jobs_dao import (
    CustomConnectorJobsDao, DaoConflictError, DaoInternalError,
    DaoResourceNotFoundError, JobStatus)
from common.storage.ddb.custom_connector_jobs_dao import \
    StartJobRequest as DaoStartJobRequest
from common.storage.ddb.custom_connector_jobs_dao import \
    StartJobResponse as DaoStartJobResponse
from common.tenant import TenantContext


class EnvironmentVariable(BaseModel):
    """Environment variable for job execution."""

    name: str
    value: str


class StartCustomConnectorJobRequest(BaseModel):
    """Request model for starting a custom connector job."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)
    environment: list[EnvironmentVariable] | None = Field(default_factory=list)


class JobDetail(BaseModel):
    """Job detail information."""

    job_id: str
    connector_id: str
    status: JobStatus
    created_at: str


class StartCustomConnectorJobResponse(BaseModel):
    """Response model for starting a custom connector job."""

    job: JobDetail


class StartCustomConnectorJobActivity:
    """
    Activity that handles starting custom connector jobs.

    1. Validating the incoming request.
    2. Calling CustomConnectorJobsDao.start_job(...) to insert a new job.
    3. Mapping DAO errors into HTTP-level exceptions.
    """

    def __init__(self, jobs_dao: CustomConnectorJobsDao):
        self.jobs_dao = jobs_dao

    def start(self, request: StartCustomConnectorJobRequest) -> Response:
        """Start a custom connector job."""
        log_context = create_log_context(
            LogContext(connector_id=request.connector_id, account_id=request.tenant_context.account_id)
        )

        try:
            logger.info("Starting custom connector job", extra=log_context)
            logger.debug(
                "Start job request details", extra={**log_context, "environment_count": len(request.environment or [])}
            )

            environment_list = []
            if request.environment is not None:
                environment_list = [env.model_dump() for env in request.environment]

            dao_req = DaoStartJobRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                environment=environment_list,
            )
            dao_resp: DaoStartJobResponse = self.jobs_dao.start_job(dao_req)

            activity_resp = StartCustomConnectorJobResponse(
                job=JobDetail(
                    job_id=dao_resp.job_id,
                    connector_id=dao_resp.connector_id,
                    status=dao_resp.status,
                    created_at=dao_resp.created_at,
                )
            )

            log_context_with_job = create_log_context(
                LogContext(
                    connector_id=request.connector_id,
                    account_id=request.tenant_context.account_id,
                    job_id=dao_resp.job_id,
                )
            )
            logger.info("Custom connector job started successfully", extra=log_context_with_job)
            logger.debug("Start job response", extra={**log_context_with_job, "response": activity_resp.model_dump()})

            return create_success_response(activity_resp, status_code=201)

        except DaoResourceNotFoundError as error:
            logger.warning("Connector or job resource not found", extra={**log_context, "error_message": error.message})
            return create_error_response(ResourceNotFoundError(error.message), status_code=404)

        except DaoConflictError as error:
            logger.warning("Cannot start job due to conflict", extra={**log_context, "error_message": error.message})
            return create_error_response(ConflictError(error.message), status_code=500)

        except DaoInternalError as error:
            logger.exception(
                "Internal error while starting custom connector job", extra={**log_context, "error": str(error)}
            )
            return create_error_response(InternalServerError(str(error)))
