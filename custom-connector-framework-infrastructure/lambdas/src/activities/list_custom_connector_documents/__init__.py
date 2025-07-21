"""Activity for listing custom connector documents."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel

from common.exceptions import InternalServerError, ResourceNotFoundError
from common.observability import logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connector_documents_dao import (
    CustomConnectorDocumentsDao, DaoInternalError, DaoResourceNotFoundError)
from common.storage.ddb.custom_connector_documents_dao import \
    ListDocumentsRequest as DaoListDocumentsRequest
from common.tenant import TenantContext


class ListCustomConnectorDocumentsRequest(BaseModel):
    """Request model for listing custom connector documents."""

    tenant_context: TenantContext
    connector_id: str
    max_results: int | None = 50
    next_token: str | None = None


class DocumentDetail(BaseModel):
    """Document detail information."""

    document_id: str
    checksum: str
    created_at: str
    updated_at: str


class ListCustomConnectorDocumentsResponse(BaseModel):
    """Response model for listing custom connector documents."""

    documents: list[DocumentDetail]
    next_token: str | None = None


class ListCustomConnectorDocumentsActivity:
    """Activity for listing custom connector documents."""

    def __init__(self, documents_dao: CustomConnectorDocumentsDao):
        self.documents_dao = documents_dao

    def list(self, request: ListCustomConnectorDocumentsRequest) -> Response:
        """List custom connector documents."""
        logger.info(
            f"ListCustomConnectorDocumentsRequest received: connector_id={request.connector_id}, "
            f"max_results={request.max_results}, next_token={request.next_token}"
        )
        try:
            dao_req = DaoListDocumentsRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
                max_results=request.max_results,
                next_token=request.next_token,
            )
            dao_resp = self.documents_dao.list_documents(dao_req)

            document_details = [
                DocumentDetail(
                    document_id=item.document_id,
                    checksum=item.checksum,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in dao_resp.documents
            ]

            activity_resp = ListCustomConnectorDocumentsResponse(
                documents=document_details,
                next_token=dao_resp.next_token,
            )
            logger.info(
                f"ListCustomConnectorDocumentsResponse: {len(document_details)} documents, "
                f"next_token={dao_resp.next_token}"
            )
            return create_success_response(activity_resp, status_code=200)

        except DaoResourceNotFoundError as error:
            logger.warning(f"Connector not found while listing documents: {error.message}")
            response = create_error_response(ResourceNotFoundError(error.message), status_code=404)
            logger.info("ListCustomConnectorDocumentsResponse: 404 Not Found")
            return response

        except DaoInternalError as error:
            logger.exception(f"Internal error while listing documents: {error.message}")
            response = create_error_response(InternalServerError(str(error)), status_code=500)
            logger.info("ListCustomConnectorDocumentsResponse: 500 Internal Server Error")
            return response
