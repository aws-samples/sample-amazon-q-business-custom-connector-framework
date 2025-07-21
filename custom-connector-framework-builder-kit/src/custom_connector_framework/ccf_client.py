"""
Custom Connector Framework (CCF) Client for interacting with the CCF API.

This module provides a client for interacting with the Custom Connector Framework API,
enabling document state management, checkpoints, and other CCF operations.
"""

from collections.abc import Mapping

import boto3
from pydantic import BaseModel, ConfigDict

from custom_connector_framework.logger import logger


class CCFDocument(BaseModel):
    """
    Represents a document stored in the Custom Connector Framework.

    This model contains metadata about documents tracked by CCF,
    including their ID, checksum, and timestamps.

    Attributes:
        document_id (str): Unique identifier for the document.
        checksum (str): Checksum of the document content and metadata.
        created_at (str): ISO-formatted timestamp of when the document was created.
        updated_at (str): ISO-formatted timestamp of when the document was last updated.

    """

    document_id: str
    checksum: str
    created_at: str
    updated_at: str


class ListDocumentsResponse(BaseModel):
    """
    Response model for list documents operation.

    Attributes:
        documents (List[CCFDocument]): List of documents returned by the API.
        next_token (Optional[str]): Pagination token for retrieving more results.

    """

    documents: list[CCFDocument]
    next_token: str | None = None


class CCFDocumentsMap(BaseModel):
    """
    Map of document IDs to their full document data.

    This immutable model provides efficient lookup of documents by ID.

    Attributes:
        documents (Dict[str, CCFDocument]): Dictionary mapping document IDs to document objects.

    """

    model_config = ConfigDict(frozen=True)  # Make it immutable
    documents: dict[str, CCFDocument]


class BatchPutDocumentsRequest(BaseModel):
    """
    Request model for batch put documents operation.

    Attributes:
        documents (List[Dict[str, str]]): List of documents to add or update.

    """

    documents: list[dict[str, str]]


class BatchDeleteDocumentsRequest(BaseModel):
    """
    Request model for batch delete documents operation.

    Attributes:
        document_ids (List[str]): List of document IDs to delete.

    """

    document_ids: list[str]


class CheckpointData(BaseModel):
    """
    Generic checkpoint data model.

    This model allows arbitrary data to be stored as checkpoint information.
    """

    model_config = ConfigDict(extra="allow")  # Allow additional fields


class Checkpoint(BaseModel):
    """
    Checkpoint model containing state data for a connector.

    Attributes:
        checkpoint_data (CheckpointData): The checkpoint data.
        connector_id (str): ID of the connector the checkpoint belongs to.

    """

    checkpoint_data: CheckpointData
    connector_id: str


class GetCheckpointResponse(BaseModel):
    """
    Response model for get checkpoint operation.

    Attributes:
        checkpoint (Checkpoint): The retrieved checkpoint.

    """

    checkpoint: Checkpoint


class PutCheckpointRequest(BaseModel):
    """
    Request model for put checkpoint operation.

    Attributes:
        checkpoint_data (Dict): The checkpoint data to store.

    """

    checkpoint_data: dict


class CCFClient:
    """
    Client wrapper for CCF document and checkpoint operations.

    This client provides methods for interacting with the Custom Connector Framework API,
    including document management and checkpoint operations.

    Attributes:
        BATCH_PUT_DOCUMENT_MAX_SIZE (int): Maximum number of documents in a batch put operation.
        BATCH_DELETE_DOCUMENT_MAX_SIZE (int): Maximum number of documents in a batch delete operation.

    """

    BATCH_PUT_DOCUMENT_MAX_SIZE = 10
    BATCH_DELETE_DOCUMENT_MAX_SIZE = 10

    def __init__(self, ccf_client: boto3.client, connector_id: str):
        """
        Initialize the CCF client.

        Args:
            ccf_client (boto3.client): Boto3 client for the CCF API.
            connector_id (str): ID of the custom connector.

        """
        self._client = ccf_client
        self._connector_id = connector_id

    def list_documents(self) -> CCFDocumentsMap:
        """
        List all documents and return a map of document IDs to their full document data.

        This method handles pagination automatically to retrieve all documents.

        Returns:
            CCFDocumentsMap: Map of document IDs to their document objects.

        """
        documents: dict[str, CCFDocument] = {}
        next_token = None

        while True:
            params = {"connector_id": self._connector_id}
            if next_token:
                params["next_token"] = next_token

            response = self._client.list_custom_connector_documents(**params)
            parsed_response = ListDocumentsResponse.model_validate(response)

            for doc in parsed_response.documents:
                documents[doc.document_id] = doc

            next_token = parsed_response.next_token
            if not next_token:
                break

        return CCFDocumentsMap(documents=documents)

    def batch_put_documents(self, document_checksums: Mapping[str, str]) -> None:
        """
        Update document checksums in CCF.

        This method handles batching according to API limits.

        Args:
            document_checksums (Mapping[str, str]): Map of document IDs to their checksums.

        """
        documents = [{"document_id": doc_id, "checksum": checksum} for doc_id, checksum in document_checksums.items()]

        # Process in batches to respect API limits
        for i in range(0, len(documents), CCFClient.BATCH_PUT_DOCUMENT_MAX_SIZE):
            batch = documents[i : i + CCFClient.BATCH_PUT_DOCUMENT_MAX_SIZE]
            request = BatchPutDocumentsRequest(documents=batch)
            self._client.batch_put_custom_connector_documents(
                connector_id=self._connector_id, **request.model_dump(exclude_none=True)
            )

    def batch_delete_documents(self, document_ids: list[str]) -> None:
        """
        Delete documents from CCF.

        This method handles batching according to API limits.

        Args:
            document_ids (List[str]): List of document IDs to delete.

        """
        # Process in batches to respect API limits
        for i in range(0, len(document_ids), CCFClient.BATCH_DELETE_DOCUMENT_MAX_SIZE):
            batch = document_ids[i : i + CCFClient.BATCH_DELETE_DOCUMENT_MAX_SIZE]
            request = BatchDeleteDocumentsRequest(document_ids=batch)
            self._client.batch_delete_custom_connector_documents(
                connector_id=self._connector_id, **request.model_dump(exclude_none=True)
            )

    def get_checkpoint(self) -> dict[str, str] | None:
        """
        Get checkpoint data for the connector.

        Checkpoints can be used to store state between connector runs, such as
        timestamps, pagination tokens, or other synchronization metadata.

        Returns:
            Optional[Dict[str, str]]: The checkpoint data as a dictionary,
                                     or None if no checkpoint exists or an error occurs.

        """
        try:
            response = self._client.get_custom_connector_checkpoint(connector_id=self._connector_id)
            if response:
                parsed_response = GetCheckpointResponse.model_validate(response)
                return parsed_response.checkpoint.checkpoint_data.model_dump()
        except Exception as error:  # pylint: disable=broad-exception-caught
            logger.warning("Failed to get checkpoint: %s", error)
        return None

    def save_checkpoint(self, checkpoint_data: dict[str, str]) -> None:
        """
        Save checkpoint data for future connector runs.

        Args:
            checkpoint_data (Dict[str, str]): The checkpoint data to save.
                                            This should contain any state needed for
                                            incremental synchronization.

        """
        request = PutCheckpointRequest(checkpoint_data=checkpoint_data)
        self._client.put_custom_connector_checkpoint(
            connector_id=self._connector_id, **request.model_dump(exclude_none=True)
        )
