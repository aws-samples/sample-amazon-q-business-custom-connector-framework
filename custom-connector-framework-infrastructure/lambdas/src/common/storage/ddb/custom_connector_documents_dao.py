"""Module for managing custom connector documents in DynamoDB."""

import json
from datetime import UTC, datetime
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table
from pydantic import BaseModel

from common.storage.ddb.custom_connectors_dao import CustomConnectorsDao
from common.storage.ddb.custom_connectors_dao import \
    DaoInternalError as ConnectorDaoInternalError
from common.storage.ddb.custom_connectors_dao import \
    DaoResourceNotFoundError as ConnectorDaoNotFoundError
from common.storage.ddb.custom_connectors_dao import GetConnectorRequest
from common.tenant import TenantContext


class DaoConflictError(Exception):
    """Exception raised when a conflict occurs in the DAO operations."""

    def __init__(self, message: str):
        super().__init__(message)


class DaoResourceNotFoundError(Exception):
    """Exception raised when a resource is not found in the DAO operations."""

    CONNECTOR_NOT_FOUND = "Connector not found"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DaoInternalError(Exception):
    """Exception raised when an internal error occurs in the DAO operations."""

    VERIFY_CONNECTOR_FAILED = "Failed to verify connector"
    PUT_DOCUMENTS_FAILED = "Failed to put documents"
    DELETE_DOCUMENTS_FAILED = "Failed to delete documents"
    LIST_DOCUMENTS_FAILED = "Failed to list documents"
    INVALID_NEXT_TOKEN = "Invalid next_token format"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DocumentItem(BaseModel):
    """Model representing a document item in the database."""

    document_id: str
    checksum: str


class BatchPutDocumentsRequest(BaseModel):
    """Request model for batch putting documents."""

    tenant_context: TenantContext
    connector_id: str
    documents: list[DocumentItem]


class BatchDeleteDocumentsRequest(BaseModel):
    """Request model for batch deleting documents."""

    tenant_context: TenantContext
    connector_id: str
    document_ids: list[str]


class ListDocumentsRequest(BaseModel):
    """Request model for listing documents."""

    tenant_context: TenantContext
    connector_id: str
    max_results: int = 50
    next_token: str | None = None


class DocumentSummary(BaseModel):
    """Model representing a document summary."""

    document_id: str
    checksum: str
    created_at: str
    updated_at: str


class ListDocumentsResponse(BaseModel):
    """Response model for listing documents."""

    documents: list[DocumentSummary]
    next_token: str | None = None


class CustomConnectorDocumentsDao:
    """Data access object for custom connector documents."""

    def __init__(self, documents_table: Table, connectors_dao: CustomConnectorsDao):
        """
        Initialize the DAO with the required tables.

        Args:
            documents_table: DynamoDB table for documents
            connectors_dao: DAO for custom connectors

        """
        self.table = documents_table
        self.connectors_dao = connectors_dao

    def _get_arn_prefix(self, tenant_context: TenantContext) -> str:
        """
        Get the ARN prefix for the tenant.

        Args:
            tenant_context: The tenant context

        Returns:
            The ARN prefix

        """
        # Explicitly cast the return value to str to satisfy mypy
        return str(tenant_context.get_arn_prefix())

    def _verify_connector_exists(self, tenant_context: TenantContext, connector_id: str) -> Any:
        """
        Verify that a connector exists.

        Args:
            tenant_context: The tenant context
            connector_id: The connector ID to verify

        Returns:
            The connector if it exists

        Raises:
            DaoResourceNotFoundError: If the connector does not exist
            DaoInternalError: If there is an internal error

        """
        try:
            get_req = GetConnectorRequest(tenant_context=tenant_context, connector_id=connector_id)
            return self.connectors_dao.get_connector(get_req)
        except ConnectorDaoNotFoundError as error:
            raise DaoResourceNotFoundError(DaoResourceNotFoundError.CONNECTOR_NOT_FOUND) from error
        except ConnectorDaoInternalError as error:
            raise DaoInternalError(DaoInternalError.VERIFY_CONNECTOR_FAILED) from error

    def batch_put_documents(self, request: BatchPutDocumentsRequest) -> None:
        """
        Batch put documents into the database.

        Args:
            request: The batch put request

        Raises:
            DaoResourceNotFoundError: If the connector does not exist
            DaoInternalError: If there is an internal error

        """
        self._verify_connector_exists(request.tenant_context, request.connector_id)
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        now_iso = datetime.now(UTC).isoformat()
        try:
            with self.table.batch_writer() as batch:
                for doc in request.documents:
                    item = {
                        "document_id": doc.document_id,
                        "custom_connector_arn_prefix": arn_prefix,
                        "connector_id": request.connector_id,
                        "checksum": doc.checksum,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                    batch.put_item(Item=item)
        except ClientError as error:
            raise DaoInternalError(DaoInternalError.PUT_DOCUMENTS_FAILED) from error

    def batch_delete_documents(self, request: BatchDeleteDocumentsRequest) -> None:
        """
        Batch delete documents from the database.

        Args:
            request: The batch delete request

        Raises:
            DaoResourceNotFoundError: If the connector does not exist
            DaoInternalError: If there is an internal error

        """
        self._verify_connector_exists(request.tenant_context, request.connector_id)
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        try:
            with self.table.batch_writer() as batch:
                for doc_id in request.document_ids:
                    batch.delete_item(Key={"document_id": doc_id, "custom_connector_arn_prefix": arn_prefix})
        except ClientError as error:
            raise DaoInternalError(DaoInternalError.DELETE_DOCUMENTS_FAILED) from error

    def list_documents(self, request: ListDocumentsRequest) -> ListDocumentsResponse:
        """
        List documents from the database.

        Args:
            request: The list documents request

        Returns:
            The list documents response

        Raises:
            DaoResourceNotFoundError: If the connector does not exist
            DaoInternalError: If there is an internal error

        """
        self._verify_connector_exists(request.tenant_context, request.connector_id)
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        query_kwargs = {
            "IndexName": "GSI1",
            "KeyConditionExpression": Key("custom_connector_arn_prefix").eq(arn_prefix)
            & Key("connector_id").eq(request.connector_id),
            "Limit": request.max_results,
        }
        if request.next_token:
            try:
                query_kwargs["ExclusiveStartKey"] = json.loads(request.next_token)
            except json.JSONDecodeError as error:
                raise DaoInternalError(DaoInternalError.INVALID_NEXT_TOKEN) from error
        try:
            response = self.table.query(**query_kwargs)
        except ClientError as error:
            raise DaoInternalError(DaoInternalError.LIST_DOCUMENTS_FAILED) from error
        items = response.get("Items", [])
        documents = [
            DocumentSummary(
                document_id=str(item["document_id"]),
                checksum=str(item["checksum"]),
                created_at=str(item["created_at"]),
                updated_at=str(item["updated_at"]),
            )
            for item in items
        ]
        last_key = response.get("LastEvaluatedKey")
        next_token = json.dumps(last_key) if last_key else None
        return ListDocumentsResponse(documents=documents, next_token=next_token)
