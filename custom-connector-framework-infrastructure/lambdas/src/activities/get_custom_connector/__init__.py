"""Activity to get custom connectors."""

from datetime import datetime
from enum import Enum

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel

from common.exceptions import InternalServerError, ResourceNotFoundError
from common.observability import LogContext, create_log_context, logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import (ContainerProperties,
                                                      CustomConnectorsDao,
                                                      DaoResourceNotFoundError)
from common.storage.ddb.custom_connectors_dao import \
    GetConnectorRequest as DaoGetConnectorRequest
from common.storage.ddb.custom_connectors_dao import \
    GetConnectorResponse as DaoGetConnectorResponse
from common.tenant import TenantContext


class ConnectorStatus(str, Enum):
    """Enum for connector status values."""

    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"


class GetCustomConnectorRequest(BaseModel):
    """Request model for getting a custom connector."""

    tenant_context: TenantContext
    connector_id: str


class ConnectorDetails(BaseModel):
    """Detailed model for connector information."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    status: ConnectorStatus
    container_properties: ContainerProperties


class GetCustomConnectorResponse(BaseModel):
    """Response model for getting a custom connector."""

    connector: ConnectorDetails


class GetCustomConnectorActivity:
    """Activity for getting custom connectors."""

    def __init__(self, dao: CustomConnectorsDao):
        self.dao = dao

    def fetch(self, request: GetCustomConnectorRequest) -> Response:
        """Fetch a custom connector by ID."""
        log_context = create_log_context(
            LogContext(connector_id=request.connector_id, account_id=request.tenant_context.account_id)
        )

        try:
            logger.info("Fetching custom connector", extra=log_context)

            dao_request = DaoGetConnectorRequest(
                tenant_context=request.tenant_context, connector_id=request.connector_id
            )

            dao_response: DaoGetConnectorResponse = self.dao.get_connector(dao_request)

            activity_response = GetCustomConnectorResponse(
                connector=ConnectorDetails(
                    connector_id=dao_response.connector_id,
                    arn=dao_response.arn,
                    name=dao_response.name,
                    created_at=dao_response.created_at,
                    updated_at=dao_response.updated_at,
                    description=dao_response.description,
                    status=ConnectorStatus(dao_response.status),
                    container_properties=dao_response.container_properties,
                )
            )

            logger.info(
                "Custom connector fetched successfully", extra={**log_context, "connector_name": dao_response.name}
            )
            logger.debug("Get connector response", extra={**log_context, "response": activity_response.model_dump()})

            return create_success_response(activity_response)

        except DaoResourceNotFoundError as error:
            logger.warning("Connector not found", extra={**log_context, "error_message": error.message})
            return create_error_response(ResourceNotFoundError(error.message), status_code=404)
        except Exception as error:
            logger.exception("Unexpected error while fetching connector", extra={**log_context, "error": str(error)})
            return create_error_response(InternalServerError(str(error)), status_code=500)
