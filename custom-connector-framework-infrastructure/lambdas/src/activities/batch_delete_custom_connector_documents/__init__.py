"""Activity to delete custom connector documents."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import InternalServerError, ResourceNotFoundError
from common.observability import logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connector_documents_dao import \
    BatchDeleteDocumentsRequest as DaoBatchDeleteDocumentsRequest
from common.storage.ddb.custom_connector_documents_dao import (
    CustomConnectorDocumentsDao, DaoInternalError, DaoResourceNotFoundError)
from common.tenant import TenantContext


class BatchDeleteCustomConnectorDocumentsRequest(BaseModel):
    """Request model for batch deleting custom connector documents."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)
    document_ids: list[str] = Field(..., min_length=1)


class BatchDeleteCustomConnectorDocumentsActivity:
    """Activity for batch deleting custom connector documents."""

    def __init__(self, documents_dao: CustomConnectorDocumentsDao):
        self.documents_dao = documents_dao

    def delete(self, request: BatchDeleteCustomConnectorDocumentsRequest) -> Response:
        """Delete multiple documents for a custom connector."""
        logger.info(
            f"BatchDeleteCustomConnectorDocumentsRequest received: "
            f"connector_id={request.connector_id}, document_count={len(request.document_ids)}"
        )
        try:
            dao_req = DaoBatchDeleteDocumentsRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                document_ids=request.document_ids,
            )
            self.documents_dao.batch_delete_documents(dao_req)
            logger.info(
                f"BatchDeleteCustomConnectorDocuments succeeded: "
                f"connector_id={request.connector_id}, document_count={len(request.document_ids)}"
            )
            response = create_success_response({}, status_code=202)
            logger.info("BatchDeleteCustomConnectorDocumentsResponse: 202 Accepted")

        except DaoResourceNotFoundError as error:
            logger.warning(f"Connector not found when deleting documents: connector_id={request.connector_id}")
            response = create_error_response(ResourceNotFoundError(str(error)), status_code=404)
            logger.info("BatchDeleteCustomConnectorDocumentsResponse: 404 Not Found")
            return response

        except DaoInternalError as error:
            logger.exception(f"Internal error while deleting documents: connector_id={request.connector_id}")
            response = create_error_response(InternalServerError(str(error)), status_code=500)
            logger.info("BatchDeleteCustomConnectorDocumentsResponse: 500 Internal Server Error")
        else:
            return response

        return response
