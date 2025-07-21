"""Activity to delete custom connector checkpoints."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import InternalServerError, ResourceNotFoundError
from common.observability import logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import (CustomConnectorsDao,
                                                      DaoInternalError,
                                                      DaoResourceNotFoundError)
from common.storage.ddb.custom_connectors_dao import \
    DeleteCheckpointRequest as DaoDeleteCheckpointRequest
from common.tenant import TenantContext


class DeleteCustomConnectorCheckpointRequest(BaseModel):
    """Request model for deleting a custom connector checkpoint."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)


class DeleteCustomConnectorCheckpointActivity:
    """Activity for deleting custom connector checkpoints."""

    def __init__(self, connectors_dao: CustomConnectorsDao):
        self.connectors_dao = connectors_dao

    def delete(self, request: DeleteCustomConnectorCheckpointRequest) -> Response:
        """Delete a checkpoint for a custom connector."""
        logger.info(f"DeleteCustomConnectorCheckpointRequest received: {request.model_dump()}")
        try:
            dao_req = DaoDeleteCheckpointRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
            )
            self.connectors_dao.delete_checkpoint(dao_req)
            logger.info(f"Checkpoint deleted successfully for connector: {request.connector_id}")
            response = create_success_response({}, status_code=202)
            logger.info("DeleteCustomConnectorCheckpointResponse: 202 Accepted")

        except DaoResourceNotFoundError as error:
            logger.warning(f"Connector or checkpoint not found when deleting: {error.message}")
            response = create_error_response(ResourceNotFoundError(error.message), status_code=404)
            logger.info("DeleteCustomConnectorCheckpointResponse: 404 Not Found")
            return response

        except DaoInternalError as error:
            logger.exception(f"Internal error while deleting checkpoint: {error.message}")
            response = create_error_response(InternalServerError(str(error)), status_code=500)
            logger.info("DeleteCustomConnectorCheckpointResponse: 500 Internal Server Error")
        else:
            return response

        return response
