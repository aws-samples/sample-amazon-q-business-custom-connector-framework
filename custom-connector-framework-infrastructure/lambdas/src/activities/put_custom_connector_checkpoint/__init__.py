"""Activity for putting custom connector checkpoints."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import (ConflictError, InternalServerError,
                               ResourceNotFoundError)
from common.observability import logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import (CustomConnectorsDao,
                                                      DaoConflictError,
                                                      DaoInternalError,
                                                      DaoResourceNotFoundError)
from common.storage.ddb.custom_connectors_dao import \
    PutCheckpointRequest as DaoPutCheckpointRequest
from common.tenant import TenantContext


class PutCustomConnectorCheckpointRequest(BaseModel):
    """Request model for putting a custom connector checkpoint."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)
    checkpoint_data: str = Field(..., min_length=1)


class PutCustomConnectorCheckpointActivity:
    """Activity for putting custom connector checkpoints."""

    def __init__(self, connectors_dao: CustomConnectorsDao):
        self.connectors_dao = connectors_dao

    def put(self, request: PutCustomConnectorCheckpointRequest) -> Response:
        """Put a checkpoint for a custom connector."""
        logger.info(f"PutCustomConnectorCheckpointRequest received: connector_id={request.connector_id}")
        try:
            dao_req = DaoPutCheckpointRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                checkpoint_data=request.checkpoint_data,
            )
            self.connectors_dao.put_checkpoint(dao_req)
            logger.info(f"Checkpoint stored successfully for connector: {request.connector_id}")
            logger.info("PutCustomConnectorCheckpointResponse: 202 Accepted")
            return create_success_response({}, status_code=202)

        except DaoResourceNotFoundError as error:
            logger.warning(f"Connector not found when putting checkpoint: {error.message}")
            response = create_error_response(ResourceNotFoundError(error.message), status_code=404)
            logger.info("PutCustomConnectorCheckpointResponse: 404 Not Found")
            return response

        except DaoConflictError as error:
            logger.warning(f"Conflict when putting checkpoint: {error.message}")
            response = create_error_response(ConflictError(error.message), status_code=409)
            logger.info("PutCustomConnectorCheckpointResponse: 409 Conflict")
            return response

        except DaoInternalError as error:
            logger.exception(f"Internal error while putting checkpoint: {error.message}")
            response = create_error_response(InternalServerError(str(error)), status_code=500)
            logger.info("PutCustomConnectorCheckpointResponse: 500 Internal Server Error")
            return response
