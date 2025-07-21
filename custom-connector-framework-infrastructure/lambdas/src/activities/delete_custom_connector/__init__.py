"""Activity to delete custom connectors."""

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel

from common.exceptions import (ConflictError, InternalServerError,
                               ResourceNotFoundError)
from common.observability import LogContext, create_log_context, logger
from common.response import create_error_response, create_success_response
from common.storage.ddb.custom_connectors_dao import (CustomConnectorsDao,
                                                      DaoConflictError,
                                                      DaoResourceNotFoundError)
from common.storage.ddb.custom_connectors_dao import \
    DeleteConnectorRequest as DaoDeleteConnectorRequest
from common.tenant import TenantContext


class DeleteCustomConnectorRequest(BaseModel):
    """Request model for deleting a custom connector."""

    tenant_context: TenantContext
    connector_id: str


class DeleteCustomConnectorActivity:
    """Activity for deleting custom connectors."""

    def __init__(self, dao: CustomConnectorsDao):
        self.dao = dao

    def delete(self, request: DeleteCustomConnectorRequest) -> Response:
        """Delete a custom connector."""
        log_context = create_log_context(
            LogContext(connector_id=request.connector_id, account_id=request.tenant_context.account_id)
        )

        try:
            logger.info("Deleting custom connector", extra=log_context)

            dao_request = DaoDeleteConnectorRequest(
                tenant_context=request.tenant_context,
                connector_id=request.connector_id,
            )

            self.dao.delete_connector(dao_request)

            logger.info("Custom connector deleted successfully", extra=log_context)
            return create_success_response(status_code=204)

        except DaoConflictError as error:
            logger.warning("Conflict while deleting connector", extra={**log_context, "error_message": error.message})
            return create_error_response(ConflictError(error.message), status_code=409)

        except DaoResourceNotFoundError as error:
            logger.warning("Connector not found", extra={**log_context, "error_message": error.message})
            return create_error_response(ResourceNotFoundError(error.message), status_code=404)

        except Exception as error:
            logger.exception("Unexpected error while deleting connector", extra={**log_context, "error": str(error)})
            return create_error_response(InternalServerError(str(error)), status_code=500)
