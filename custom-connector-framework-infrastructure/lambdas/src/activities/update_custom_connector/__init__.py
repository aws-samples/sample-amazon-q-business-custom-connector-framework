"""
Activity for updating a custom connector.

This module implements the activity for updating an existing custom connector.
It handles validation, error handling, and delegates to the DAO layer for persistence.
The implementation uses version-based optimistic locking to prevent concurrent updates.
"""

from datetime import datetime

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import (ConflictError, InternalServerError,
                               ResourceNotFoundError)
from common.observability import logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import (ConnectorStatus,
                                                      CustomConnectorsDao,
                                                      DaoConflictError,
                                                      DaoResourceNotFoundError)
from common.storage.ddb.custom_connectors_dao import \
    UpdateConnectorRequest as DaoUpdateConnectorRequest
from common.storage.ddb.custom_connectors_dao import \
    UpdateConnectorResponse as DaoUpdateConnectorResponse
from common.storage.ddb.custom_connectors_dao import \
    UpdateContainerProperties as DaoUpdateContainerProperties
from common.storage.ddb.custom_connectors_dao import \
    UpdateResourceRequirements as DaoUpdateResourceRequirements
from common.tenant import TenantContext


class UpdateResourceRequirements(BaseModel):
    """Resource requirements for container execution in update operations."""

    cpu: float | None = Field(default=None)
    memory: int | None = Field(default=None)


class UpdateContainerProperties(BaseModel):
    """Container properties for custom connector execution in update operations."""

    execution_role_arn: str | None = Field(default=None)
    image_uri: str | None = Field(default=None)
    job_role_arn: str | None = Field(default=None)
    resource_requirements: UpdateResourceRequirements | None = Field(default=None)
    timeout: int | None = Field(default=None, ge=0)


class UpdateCustomConnectorRequest(BaseModel):
    """Request model for updating a custom connector."""

    tenant_context: TenantContext
    connector_id: str
    name: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9-]+$")
    description: str | None = Field(default=None, max_length=1000)
    container_properties: UpdateContainerProperties | None = None


class ConnectorSummary(BaseModel):
    """Summary information about a connector."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: ConnectorStatus
    description: str | None = None


class UpdateCustomConnectorResponse(BaseModel):
    """Response model for updating a custom connector."""

    connector: ConnectorSummary


class UpdateCustomConnectorActivity:
    """Activity for updating custom connectors."""

    def __init__(self, dao: CustomConnectorsDao):
        self.dao = dao

    def update(self, request: UpdateCustomConnectorRequest) -> Response:
        """
        Update a custom connector with the provided information.

        This method validates the update request, delegates to the DAO layer for persistence,
        and handles any errors that occur during the update process. It transforms between
        the API-level models and the DAO-level models.

        Args:
            request (UpdateCustomConnectorRequest): Contains connector ID and fields to update

        Returns:
            Response: HTTP response with updated connector information or error details

        """
        try:
            logger.info(f"Updating connector with ID: {request.connector_id}")

            # Convert the activity request to a DAO request
            dao_container_properties = None
            if request.container_properties:
                # Convert activity UpdateContainerProperties to DAO UpdateContainerProperties
                dao_resource_reqs = None
                if request.container_properties.resource_requirements:
                    dao_resource_reqs = DaoUpdateResourceRequirements(
                        cpu=request.container_properties.resource_requirements.cpu,
                        memory=request.container_properties.resource_requirements.memory,
                    )

                dao_container_properties = DaoUpdateContainerProperties(
                    execution_role_arn=request.container_properties.execution_role_arn,
                    image_uri=request.container_properties.image_uri,
                    job_role_arn=request.container_properties.job_role_arn,
                    resource_requirements=dao_resource_reqs,
                    timeout=request.container_properties.timeout,
                )

            dao_request = DaoUpdateConnectorRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                name=request.name,
                description=request.description,
                container_properties=dao_container_properties,
            )

            # Call the DAO to update the connector
            dao_response: DaoUpdateConnectorResponse = self.dao.update_connector(dao_request)

            # Convert the DAO response to an activity response
            activity_response = UpdateCustomConnectorResponse(
                connector=ConnectorSummary(
                    connector_id=dao_response.connector_id,
                    arn=dao_response.arn,
                    name=dao_response.name,
                    created_at=dao_response.created_at,
                    updated_at=dao_response.updated_at,
                    status=dao_response.status,
                    description=dao_response.description,
                )
            )

            logger.info(f"Connector updated successfully: {dao_response.connector_id}")
            return create_success_response(activity_response)

        except DaoResourceNotFoundError as error:
            logger.warning(f"Connector not found: {error.message}")
            return create_error_response(ResourceNotFoundError(error.message), status_code=404)
        except DaoConflictError as error:
            logger.warning(f"Conflict while updating connector: {error.message}")
            return create_error_response(ConflictError(error.message), status_code=409)
        except Exception as error:
            logger.exception("Unexpected error while updating connector")
            return create_error_response(InternalServerError(str(error)), status_code=500)
