"""Activity to get custom connector checkpoints."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import InternalServerError, ResourceNotFoundError
from common.observability import logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import (CustomConnectorsDao,
                                                      DaoInternalError,
                                                      DaoResourceNotFoundError)
from common.storage.ddb.custom_connectors_dao import \
    GetCheckpointRequest as DaoGetCheckpointRequest
from common.storage.ddb.custom_connectors_dao import \
    GetCheckpointResponse as DaoGetCheckpointResponse
from common.tenant import TenantContext


class GetCustomConnectorCheckpointRequest(BaseModel):
    """Request model for getting a custom connector checkpoint."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)


class CheckpointDetail(BaseModel):
    """Model for checkpoint detail information."""

    checkpoint_data: str
    created_at: str
    updated_at: str


class GetCustomConnectorCheckpointResponse(BaseModel):
    """Response model for getting a custom connector checkpoint."""

    checkpoint: CheckpointDetail


class GetCustomConnectorCheckpointActivity:
    """Activity for getting custom connector checkpoints."""

    def __init__(self, connectors_dao: CustomConnectorsDao):
        self.connectors_dao = connectors_dao

    def fetch(self, request: GetCustomConnectorCheckpointRequest) -> Response:
        """Fetch a checkpoint for a custom connector."""
        logger.info(f"GetCustomConnectorCheckpointRequest received: {request.model_dump()}")
        try:
            dao_req = DaoGetCheckpointRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
            )
            dao_resp: DaoGetCheckpointResponse = self.connectors_dao.get_checkpoint(dao_req)

            detail = CheckpointDetail(
                checkpoint_data=dao_resp.checkpoint.checkpoint_data,
                created_at=dao_resp.checkpoint.created_at,
                updated_at=dao_resp.checkpoint.updated_at,
            )
            activity_resp = GetCustomConnectorCheckpointResponse(checkpoint=detail)

            logger.info(f"GetCustomConnectorCheckpointResponse: {activity_resp.model_dump()}")
            return create_success_response(activity_resp, status_code=200)

        except DaoResourceNotFoundError as error:
            logger.warning(f"Connector or checkpoint not found: {error.message}")
            response = create_error_response(ResourceNotFoundError(error.message), status_code=404)
            logger.info("GetCustomConnectorCheckpointResponse: 404 Not Found")
            return response

        except DaoInternalError as error:
            logger.exception(f"Internal error while retrieving checkpoint: {error.message}")
            response = create_error_response(InternalServerError(str(error)), status_code=500)
            logger.info("GetCustomConnectorCheckpointResponse: 500 Internal Server Error")
            return response
