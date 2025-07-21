"""Activity to put custom connector documents."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel, Field

from common.exceptions import (ConflictError, InternalServerError,
                               ResourceNotFoundError)
from common.observability import LogContext, create_log_context, logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connector_documents_dao import \
    BatchPutDocumentsRequest as DaoBatchPutDocumentsRequest
from common.storage.ddb.custom_connector_documents_dao import (
    CustomConnectorDocumentsDao, DaoConflictError, DaoInternalError,
    DaoResourceNotFoundError)
from common.storage.ddb.custom_connector_documents_dao import \
    DocumentItem as DaoDocumentItem
from common.tenant import TenantContext


class BatchPutCustomConnectorDocumentsRequest(BaseModel):
    """Request model for batch putting custom connector documents."""

    tenant_context: TenantContext
    connector_id: str = Field(..., min_length=1)
    documents: list[DaoDocumentItem] = Field(..., min_length=1)


class BatchPutCustomConnectorDocumentsActivity:
    """Activity for batch putting custom connector documents."""

    def __init__(self, documents_dao: CustomConnectorDocumentsDao):
        self.documents_dao = documents_dao

    def put(self, request: BatchPutCustomConnectorDocumentsRequest) -> Response:
        """Put multiple documents for a custom connector."""
        log_context = create_log_context(
            LogContext(connector_id=request.connector_id, account_id=request.tenant_context.account_id)
        )

        try:
            logger.info(
                "Batch putting custom connector documents",
                extra={**log_context, "document_count": len(request.documents)},
            )
            logger.debug(
                "Batch put documents request details",
                extra={**log_context, "request": request.model_dump(exclude={"tenant_context", "documents"})},
            )

            dao_req = DaoBatchPutDocumentsRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                documents=request.documents,
            )
            self.documents_dao.batch_put_documents(dao_req)

            logger.info(
                "Batch put documents completed successfully",
                extra={**log_context, "document_count": len(request.documents)},
            )
            return create_success_response({}, status_code=202)

        except DaoResourceNotFoundError as error:
            logger.warning(
                "Connector not found when putting documents", extra={**log_context, "error_message": error.message}
            )
            return create_error_response(ResourceNotFoundError(error.message), status_code=404)

        except DaoConflictError as error:
            logger.warning("Conflict when putting documents", extra={**log_context, "error_message": error.message})
            return create_error_response(ConflictError(error.message), status_code=409)

        except DaoInternalError as error:
            logger.exception("Internal error while putting documents", extra={**log_context, "error": str(error)})
            return create_error_response(InternalServerError(str(error)), status_code=500)
