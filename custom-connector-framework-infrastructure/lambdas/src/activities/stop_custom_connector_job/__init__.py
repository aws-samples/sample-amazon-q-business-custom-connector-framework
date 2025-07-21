"""Activity for stopping custom connector jobs."""

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
    UpdateJobStatusRequest as DaoUpdateJobStatusRequest
from common.tenant import TenantContext


class StopCustomConnectorJobRequest(BaseModel):
    """Request model for stopping a custom connector job."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)
    job_id: str = Field(..., min_length=1)
    batch_job_id: str | None = None


class StopCustomConnectorJobActivity:
    """Activity for stopping custom connector jobs."""

    def __init__(self, jobs_dao: CustomConnectorJobsDao):
        self.jobs_dao = jobs_dao

    def stop(self, request: StopCustomConnectorJobRequest) -> Response:
        """Stop a custom connector job by updating its status to STOPPING."""
        log_context = create_log_context(
            LogContext(
                connector_id=request.connector_id, account_id=request.tenant_context.account_id, job_id=request.job_id
            )
        )

        try:
            logger.info("Stopping custom connector job", extra=log_context)
            logger.debug("Stop job request details", extra={**log_context, "batch_job_id": request.batch_job_id})

            dao_req = DaoUpdateJobStatusRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                job_id=request.job_id,
                status=JobStatus.STOPPING,
                batch_job_id=request.batch_job_id,
            )
            self.jobs_dao.update_job_status(dao_req)

            logger.info("Custom connector job marked as STOPPING", extra=log_context)
            return create_success_response({}, status_code=202)

        except DaoResourceNotFoundError as error:
            logger.warning(
                "Resource not found while stopping job", extra={**log_context, "error_message": error.message}
            )
            return create_error_response(ResourceNotFoundError(error.message), status_code=404)

        except DaoConflictError as error:
            logger.warning("Conflict while stopping job", extra={**log_context, "error_message": error.message})
            return create_error_response(ConflictError(error.message), status_code=409)

        except DaoInternalError as error:
            logger.exception("Internal error while stopping job", extra={**log_context, "error": str(error)})
            return create_error_response(InternalServerError(str(error)), status_code=500)
