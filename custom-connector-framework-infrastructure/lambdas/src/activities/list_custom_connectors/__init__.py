"""Activity for listing custom connectors."""

from datetime import datetime
from enum import Enum

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import InternalServerError
from common.observability import LogContext, create_log_context, logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import CustomConnectorsDao
from common.storage.ddb.custom_connectors_dao import \
    ListConnectorsRequest as DaoListConnectorsRequest
from common.storage.ddb.custom_connectors_dao import \
    ListConnectorsResponse as DaoListConnectorsResponse
from common.tenant import TenantContext


class ConnectorStatus(str, Enum):
    """Connector status enumeration."""

    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"


class ConnectorSummary(BaseModel):
    """Summary information for a connector."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: ConnectorStatus
    description: str | None = None


class ListCustomConnectorsRequest(BaseModel):
    """Request model for listing custom connectors."""

    tenant_context: TenantContext
    max_results: int | None = Field(default=50, ge=1, le=100)
    next_token: str | None = None


class ListCustomConnectorsResponse(BaseModel):
    """Response model for listing custom connectors."""

    connectors: list[ConnectorSummary]
    next_token: str | None = None


class ListCustomConnectorsActivity:
    """Activity for listing custom connectors."""

    def __init__(self, dao: CustomConnectorsDao):
        self.dao = dao

    def list(self, request: ListCustomConnectorsRequest) -> Response:
        """List custom connectors."""
        log_context = create_log_context(LogContext(account_id=request.tenant_context.account_id))

        try:
            logger.info("Listing custom connectors", extra={**log_context, "max_results": request.max_results})
            logger.debug(
                "List connectors request details",
                extra={**log_context, "request": request.model_dump(exclude={"tenant_context"})},
            )

            dao_request = DaoListConnectorsRequest(
                tenant_context=request.tenant_context, max_results=request.max_results, next_token=request.next_token
            )

            dao_response: DaoListConnectorsResponse = self.dao.list_connectors(dao_request)

            connector_summaries = [
                ConnectorSummary(
                    connector_id=connector.connector_id,
                    arn=connector.arn,
                    name=connector.name,
                    created_at=connector.created_at,
                    updated_at=connector.updated_at,
                    status=ConnectorStatus(connector.status),
                    description=connector.description,
                )
                for connector in dao_response.connectors
            ]

            response = ListCustomConnectorsResponse(connectors=connector_summaries, next_token=dao_response.next_token)

            logger.info(
                "Custom connectors listed successfully",
                extra={
                    **log_context,
                    "connector_count": len(connector_summaries),
                    "has_next_token": dao_response.next_token is not None,
                },
            )
            logger.debug("List connectors response", extra={**log_context, "response": response.model_dump()})

            return create_success_response(response)

        except Exception as error:
            logger.exception("Error in ListCustomConnectorsActivity", extra={**log_context, "error": str(error)})
            return create_error_response(InternalServerError(str(error)), status_code=500)
