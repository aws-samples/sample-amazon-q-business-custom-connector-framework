"""
Amazon Q Business Custom Connector Interface implementation.

This module provides the concrete implementation of the BaseCustomConnectorInterface
for Amazon Q Business, handling document synchronization, content transformation,
and interaction with the Amazon Q Business API.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, ClassVar, Optional

import boto3

from custom_connector_framework.base_custom_connector_interfaces import BaseCustomConnectorInterface
from custom_connector_framework.ccf_client import CCFClient
from custom_connector_framework.logger import logger
from custom_connector_framework.models.document import Document
from custom_connector_framework.models.qbusiness import (
    AccessConfiguration,
    BatchDeleteDocumentRequest,
    BatchPutDocumentRequest,
    DocumentAttribute,
    DocumentContent,
    DocumentToDelete,
    MemberRelation,
    QBusinessDocument,
    Value,
)
from custom_connector_framework.utils import JsonSerializer

if TYPE_CHECKING:
    from mypy_boto3_qbusiness.client import QBusinessClient
    from mypy_boto3_s3.client import S3Client
else:
    QBusinessClient = boto3.client
    S3Client = boto3.client


class QBusinessConstants:  # pylint: disable=too-few-public-methods
    """
    Constants defining Amazon Q Business API limits and constraints.

    These constants are used to ensure that batch operations conform to
    the service limits imposed by the Amazon Q Business API.
    """

    BATCH_LIMITS: ClassVar[dict[str, int]] = {
        "PUT_MAX_DOCS": 10,  # Maximum number of documents in a single BatchPutDocument request
        "PUT_MAX_TOTAL_SIZE": 10 * 1024 * 1024,  # 10MB maximum total size for a batch
        "PUT_MAX_SINGLE_SIZE": 50 * 1024 * 1024,  # 50MB maximum size for a single document
        "DELETE_MAX_DOCS": 10,  # Maximum number of documents in a single BatchDeleteDocument request
    }


class QBusinessCustomConnectorInterface(BaseCustomConnectorInterface):
    """
    Implementation of the BaseCustomConnectorInterface for Amazon Q Business.

    This class handles the synchronization of documents with Amazon Q Business,
    including document transformation, batching, and API interactions.

    Attributes:
        _qbusiness_client: Amazon Q Business API client.
        _application_id: Amazon Q Business application ID.
        _index_id: Amazon Q Business index ID.
        _data_source_id: Amazon Q Business data source ID.
        _s3_client: S3 client for handling large documents.
        _s3_bucket: S3 bucket name for storing large documents.
        _sync_job_id: Current sync job ID.

    """

    def __init__(  # noqa: PLR0913
        self,
        qbusiness_client: boto3.client,
        qbusiness_app_id: str,
        qbusiness_index_id: str,
        qbusiness_data_source_id: str,
        ccf_client: Optional[CCFClient] = None,
        s3_client: Optional[boto3.client] = None,
        s3_bucket: Optional[str] = None,
    ):
        super().__init__(ccf_client)
        self._qbusiness_client = qbusiness_client
        self._application_id = qbusiness_app_id
        self._index_id = qbusiness_index_id
        self._data_source_id = qbusiness_data_source_id
        self._s3_client = s3_client
        self._s3_bucket = s3_bucket
        self._sync_job_id = None

    def sync(self) -> None:
        """
        Synchronize documents with Amazon Q Business.

        This method orchestrates the entire synchronization process:
        1. Starts a sync job with Amazon Q Business
        2. Retrieves documents to add/update and delete
        3. Optimizes document processing using checksums (if CCF client is available)
        4. Uploads new/modified documents in batches
        5. Deletes removed documents in batches
        6. Updates document state in CCF (if CCF client is available)
        7. Stops the sync job when complete

        Raises:
            Exception: Any exception that occurs during synchronization.

        """
        try:
            logger.info("Starting sync job for data source %s...", self._data_source_id)
            self._sync_job_id = self._start_sync_job()

            try:
                # Get documents using interface methods
                current_docs = list(self.get_documents_to_add())
                logger.info("Processing %s documents to upload", len(current_docs))
                documents_to_delete = list(self.get_documents_to_delete())
                logger.info("Processing %s documents to delete", len(documents_to_delete))

                # If CCF is enabled, use checksums to optimize sync
                if self.ccf_client:
                    # Calculate checksums for current documents
                    current_checksums = {doc.id: doc.get_checksum() for doc in current_docs}

                    # Get existing CCF document states
                    ccf_docs = self.ccf_client.list_documents()

                    logger.info("There are %s checksums from custom connector framework", len(ccf_docs.documents))
                    # Filter documents that need updating
                    docs_to_sync = []
                    for doc in current_docs:
                        if doc.id not in ccf_docs.documents:
                            logger.debug("New document found: %s", doc.id)
                            docs_to_sync.append(doc)
                        elif ccf_docs.documents[doc.id].checksum != current_checksums[doc.id]:
                            logger.debug("Document changed: %s", doc.id)
                            docs_to_sync.append(doc)

                    current_docs = docs_to_sync

                    logger.info("There are %s current documents to sync after comparing checksums", len(current_docs))

                # Sync changes with Q Business
                if current_docs:
                    self._batch_put_documents(iter(current_docs))

                    # Update CCF with new checksums if enabled
                    if self.ccf_client:
                        checksums_to_update = {doc.id: doc.get_checksum() for doc in current_docs}
                        logger.info("Updating custom connector documents api with %s", len(checksums_to_update))
                        self.ccf_client.batch_put_documents(checksums_to_update)

                if documents_to_delete:
                    self._batch_delete_documents(iter(documents_to_delete))

                    # Remove deleted documents from CCF if enabled
                    if self.ccf_client:
                        self.ccf_client.batch_delete_documents(documents_to_delete)

            finally:
                if self._sync_job_id:
                    self._stop_sync_job()
        except Exception as error:
            logger.warning("Sync operation failed: %s", error)
            raise

    def _start_sync_job(self) -> str:
        """
        Start a data source sync job in Amazon Q Business.

        Returns:
            str: The execution ID of the sync job.

        """
        params = {
            "applicationId": self._application_id,
            "indexId": self._index_id,
            "dataSourceId": self._data_source_id,
        }
        response = self._qbusiness_client.start_data_source_sync_job(**params)
        return response["executionId"]

    def _stop_sync_job(self) -> None:
        """Stop the current data source sync job in Amazon Q Business."""
        params = {
            "applicationId": self._application_id,
            "indexId": self._index_id,
            "dataSourceId": self._data_source_id,
        }
        self._qbusiness_client.stop_data_source_sync_job(**params)

    def _handle_large_document(self, doc: Document) -> dict[str, str] | None:
        """
        Upload a large document to S3 for processing by Amazon Q Business.

        This method is used when a document exceeds the size limit for direct API upload.

        Args:
            doc (Document): The document to upload to S3.

        Returns:
            Optional[Dict[str, str]]: S3 location information if successful, None otherwise.

        """
        if not self._s3_client or not self._s3_bucket:
            logger.warning("Skipping document %s > 10MB: S3 not configured.", doc.id)
            return None

        try:
            key = f"qbusiness-docs/{doc.id}{doc.file.file_path.suffix}"
            with open(doc.file.file_path, "rb") as file_handle:
                self._s3_client.put_object(Bucket=self._s3_bucket, Key=key, Body=file_handle.read())
        except Exception as error:  # pylint: disable=broad-exception-caught
            logger.error("Failed to upload document %s to S3: %s", doc.id, error)
            return None
        return {"bucket": self._s3_bucket, "key": key}

    def _prepare_document_for_upload(self, doc: Document) -> QBusinessDocument | None:
        """
        Transform a Document object into a QBusinessDocument for API upload.

        This method handles content extraction, attribute mapping, and access control configuration.
        It also manages large documents by uploading them to S3 when necessary.

        Args:
            doc (Document): The document to prepare for upload.

        Returns:
            Optional[QBusinessDocument]: The prepared document, or None if preparation fails.

        Raises:
            Exception: Any exception that occurs during document preparation.

        """
        try:
            content_type = doc.file.infer_content_type()
            file_size = doc.file.get_size()

            # Skip documents that exceed the maximum allowed size
            if file_size > QBusinessConstants.BATCH_LIMITS["PUT_MAX_SINGLE_SIZE"]:
                logger.warning("Skipping document %s due to size > 50MB.", doc.id)
                return None

            # Handle document content based on size
            if file_size > QBusinessConstants.BATCH_LIMITS["PUT_MAX_TOTAL_SIZE"]:
                # For large documents (>10MB), upload to S3
                s3_info = self._handle_large_document(doc)
                if not s3_info:
                    return None
                content = DocumentContent(s3=s3_info)
            else:
                # For smaller documents, include content directly
                with open(doc.file.file_path, "rb") as file_handle:
                    content = DocumentContent(blob=file_handle.read())

            # Create standard attributes
            attributes = [
                DocumentAttribute(
                    name="_source_uri",
                    value=Value(stringValue=doc.metadata.source_uri),
                )
            ]
            if doc.metadata.last_updated_at:
                attributes.append(
                    DocumentAttribute(
                        name="_last_updated_at",
                        value=Value(stringValue=doc.metadata.last_updated_at),
                    )
                )
            if doc.metadata.created_at:
                attributes.append(
                    DocumentAttribute(
                        name="_created_at",
                        value=Value(stringValue=doc.metadata.created_at),
                    )
                )

            # Add custom attributes
            for name, value in doc.metadata.attributes.items():
                attributes.append(DocumentAttribute(name=name, value=Value(stringValue=str(value))))

            # Create access configuration
            access_config = None
            if doc.metadata.access_control_list:
                access_config = AccessConfiguration(
                    accessControls=doc.metadata.access_control_list, memberRelation=MemberRelation.AND
                )

            return QBusinessDocument(
                id=doc.id,
                title=doc.metadata.title,
                contentType=content_type,
                content=content,
                attributes=attributes,
                accessConfiguration=access_config,
            )

        except Exception as error:
            logger.warning("Failed to prepare document %s: %s", doc.id, error)
            raise

    def _batch_put_documents(self, documents: Iterator[Document]) -> None:
        """
        Upload documents to Amazon Q Business in batches.

        This method handles batching documents according to Amazon Q Business API limits.

        Args:
            documents (Iterator[Document]): Documents to upload.

        """
        batch = []
        size_accumulator = 0

        for doc in documents:
            prepared_doc = self._prepare_document_for_upload(doc)
            if not prepared_doc:
                continue

            file_size = doc.file.get_size()
            batch.append(prepared_doc)
            size_accumulator += file_size

            # Send batch when size limits are reached
            if (
                len(batch) == QBusinessConstants.BATCH_LIMITS["PUT_MAX_DOCS"]
                or size_accumulator >= QBusinessConstants.BATCH_LIMITS["PUT_MAX_TOTAL_SIZE"]
            ):
                self._qbusiness_batch_put_documents(batch)
                batch = []
                size_accumulator = 0

        # Send any remaining documents
        if batch:
            self._qbusiness_batch_put_documents(batch)

    def _qbusiness_batch_put_documents(self, batch: list[QBusinessDocument]) -> None:
        """
        Make a BatchPutDocument API call to Amazon Q Business.

        Args:
            batch (List[QBusinessDocument]): List of documents to upload.

        """
        try:
            request = BatchPutDocumentRequest(
                applicationId=self._application_id,
                indexId=self._index_id,
                documents=batch,
                dataSourceSyncId=self._sync_job_id,
            )

            # Serialize the request to format expected by boto3
            serialized_request = JsonSerializer.serialize(request.model_dump(by_alias=True, exclude_none=True))
            response = self._qbusiness_client.batch_put_document(**serialized_request)

            # Log any failures
            if "failedDocuments" in response:
                for failed_doc in response["failedDocuments"]:
                    logger.error("Failed to upload document %s: Error: %s", failed_doc["id"], failed_doc)
        except Exception as error:  # pylint: disable=broad-exception-caught
            logger.error("Failed to batch upload documents: %s", error)

    def _batch_delete_documents(self, document_ids: Iterator[str]) -> None:
        """
        Delete documents from Amazon Q Business in batches.

        This method handles batching document deletions according to Amazon Q Business API limits.

        Args:
            document_ids (Iterator[str]): IDs of documents to delete.

        """
        batch = []
        for doc_id in document_ids:
            batch.append(DocumentToDelete(documentId=doc_id))

            # Send batch when size limit is reached
            if len(batch) == QBusinessConstants.BATCH_LIMITS["DELETE_MAX_DOCS"]:
                self._qbusiness_batch_delete_documents(batch)
                batch = []

        # Send any remaining documents
        if batch:
            self._qbusiness_batch_delete_documents(batch)

    def _qbusiness_batch_delete_documents(self, batch: list[DocumentToDelete]) -> None:
        """
        Make a BatchDeleteDocument API call to Amazon Q Business.

        Args:
            batch (List[DocumentToDelete]): List of document IDs to delete.

        """
        try:
            request = BatchDeleteDocumentRequest(
                applicationId=self._application_id,
                indexId=self._index_id,
                documents=batch,
                dataSourceSyncId=self._sync_job_id,
            )

            # Serialize the request to format expected by boto3
            serialized_request = JsonSerializer.serialize(request.model_dump(by_alias=True, exclude_none=True))
            response = self._qbusiness_client.batch_delete_document(**serialized_request)

            # Log any failures
            if "failedDocuments" in response:
                for failed_doc in response["failedDocuments"]:
                    logger.error(
                        "Failed to delete document %s: Error: %s",
                        failed_doc["id"],
                        failed_doc.get("errorMessage", "Unknown error"),
                    )
        except Exception as error:  # pylint: disable=broad-exception-caught
            logger.error("Failed to batch delete documents: %s", error)
