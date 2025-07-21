"""Activity for listing custom connector jobs."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import InternalServerError, ResourceNotFoundError
from common.observability import logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connector_jobs_dao import (
    CustomConnectorJobsDao, DaoInternalError, DaoResourceNotFoundError)
from common.storage.ddb.custom_connector_jobs_dao import \
    JobStatus as DaoJobStatus
from common.storage.ddb.custom_connector_jobs_dao import \
    ListJobsRequest as DaoListJobsRequest
from common.storage.ddb.custom_connector_jobs_dao import \
    ListJobsResponse as DaoListJobsResponse
from common.tenant import TenantContext


class ListCustomConnectorJobsRequest(BaseModel):
    """Request model for listing custom connector jobs."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)
    max_results: int | None = Field(default=50, gt=0)
    next_token: str | None = None
    status: DaoJobStatus | None = None


class JobDetail(BaseModel):
    """Job detail information."""

    job_id: str
    connector_id: str
    status: DaoJobStatus
    created_at: str


class ListCustomConnectorJobsResponse(BaseModel):
    """Response model for listing custom connector jobs."""

    jobs: list[JobDetail]
    next_token: str | None = None


class ListCustomConnectorJobsActivity:
    """Activity for listing custom connector jobs."""

    def __init__(self, jobs_dao: CustomConnectorJobsDao):
        self.jobs_dao = jobs_dao

    def list(self, request: ListCustomConnectorJobsRequest) -> Response:
        """List custom connector jobs."""
        logger.info(
            f"ListCustomConnectorJobsRequest received: connector_id={request.connector_id}, "
            f"max_results={request.max_results}, next_token={request.next_token}, status={request.status}"
        )
        try:
            dao_req = DaoListJobsRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                max_results=request.max_results,
                next_token=request.next_token,
                status=request.status,
            )
            dao_resp: DaoListJobsResponse = self.jobs_dao.list_jobs(dao_req)

            job_details = [
                JobDetail(
                    job_id=job.job_id,
                    connector_id=job.connector_id,
                    status=job.status,
                    created_at=job.created_at,
                )
                for job in dao_resp.jobs
            ]

            activity_resp = ListCustomConnectorJobsResponse(
                jobs=job_details,
                next_token=dao_resp.next_token,
            )
            logger.info(f"ListCustomConnectorJobsResponse: {len(job_details)} jobs, next_token={dao_resp.next_token}")
            return create_success_response(activity_resp, status_code=200)

        except DaoResourceNotFoundError as error:
            logger.warning(f"Resource not found while listing jobs: {error.message}")
            response = create_error_response(ResourceNotFoundError(error.message), status_code=404)
            logger.info("ListCustomConnectorJobsResponse: 404 Not Found")
            return response

        except DaoInternalError as error:
            logger.exception(f"Internal error while listing jobs: {error.message}")
            response = create_error_response(InternalServerError(str(error)), status_code=500)
            logger.info("ListCustomConnectorJobsResponse: 500 Internal Server Error")
            return response
