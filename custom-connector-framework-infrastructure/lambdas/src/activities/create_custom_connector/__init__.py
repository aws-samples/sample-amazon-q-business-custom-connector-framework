"""Activity to create custom connectors."""

from datetime import datetime
from enum import Enum

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import ConflictError, InternalServerError
from common.observability import LogContext, create_log_context, logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import \
    ContainerProperties as DaoContainerProperties
from common.storage.ddb.custom_connectors_dao import \
    CreateConnectorRequest as DaoCreateConnectorRequest
from common.storage.ddb.custom_connectors_dao import \
    CreateConnectorResponse as DaoCreateConnectorResponse
from common.storage.ddb.custom_connectors_dao import (CustomConnectorsDao,
                                                      DaoConflictError)
from common.tenant import TenantContext


class ConnectorStatus(str, Enum):
    """Enum for connector status values."""

    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"


class ResourceRequirements(BaseModel):
    """Model for container resource requirements."""

    cpu: float | None = Field(default=1)
    memory: int | None = Field(default=2048)


class ContainerProperties(BaseModel):
    """Model for container properties configuration."""

    execution_role_arn: str
    image_uri: str
    job_role_arn: str
    resource_requirements: ResourceRequirements | None = Field(default=ResourceRequirements())
    timeout: int = Field(default=3600, ge=0)


class CreateCustomConnectorRequest(BaseModel):
    """Request model for creating a custom connector."""

    tenant_context: TenantContext
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9-]+$")
    description: str | None = Field(default=None, max_length=1000)
    container_properties: ContainerProperties


class ConnectorSummary(BaseModel):
    """Summary model for connector information."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: ConnectorStatus
    description: str | None = None


class CreateCustomConnectorResponse(BaseModel):
    """Response model for creating a custom connector."""

    connector: ConnectorSummary


class CreateCustomConnectorActivity:
    """Activity for creating custom connectors."""

    def __init__(self, dao: CustomConnectorsDao):
        self.dao = dao

    def create(self, request: CreateCustomConnectorRequest) -> Response:
        """Create a new custom connector."""
        log_context = create_log_context(LogContext(account_id=request.tenant_context.account_id))

        try:
            logger.info("Creating custom connector", extra={**log_context, "connector_name": request.name})
            logger.debug(
                "Create connector request details",
                extra={**log_context, "request": request.model_dump(exclude={"tenant_context"})},
            )

            dao_request = DaoCreateConnectorRequest(
                tenant_context=request.tenant_context,
                name=request.name,
                description=request.description,
                container_properties=DaoContainerProperties(**request.container_properties.model_dump()),
            )

            dao_response: DaoCreateConnectorResponse = self.dao.create_connector(dao_request)

            activity_response = CreateCustomConnectorResponse(
                connector=ConnectorSummary(
                    connector_id=dao_response.connector_id,
                    arn=dao_response.arn,
                    name=dao_response.name,
                    created_at=dao_response.created_at,
                    updated_at=dao_response.updated_at,
                    status=ConnectorStatus(dao_response.status),
                    description=request.description,
                )
            )

            log_context_with_id = create_log_context(
                LogContext(connector_id=dao_response.connector_id, account_id=request.tenant_context.account_id)
            )
            logger.info("Custom connector created successfully", extra=log_context_with_id)
            logger.debug(
                "Create connector response", extra={**log_context_with_id, "response": activity_response.model_dump()}
            )

            return create_success_response(activity_response, status_code=201)

        except DaoConflictError as error:
            logger.warning(
                "Conflict while creating connector",
                extra={**log_context, "error_message": error.message, "connector_name": request.name},
            )
            return create_error_response(ConflictError(error.message), status_code=409)
        except Exception as error:
            logger.exception(
                "Unexpected error while creating connector",
                extra={**log_context, "error": str(error), "connector_name": request.name},
            )
            return create_error_response(InternalServerError(str(error)))
