"""
Base interface for custom connectors in the Amazon Q Business Custom Connector Framework.

This module defines the abstract base class that all custom connectors must implement,
providing core functionality for document synchronization and state management.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator

from custom_connector_framework.ccf_client import CCFClient, CCFDocumentsMap
from custom_connector_framework.models.document import Document


class BaseCustomConnectorInterface(ABC):
    """
    Abstract base class for custom connectors.

    This class defines the core interface that all custom connectors must implement,
    providing methods for document synchronization and state management.

    Attributes:
        ccf_client (Optional[CCFClient]): Client for interacting with the Custom Connector Framework API.

    """

    def __init__(self, ccf_client: CCFClient | None = None):
        """
        Initialize the base custom connector interface.

        Args:
            ccf_client (Optional[CCFClient]): Client for interacting with the Custom Connector Framework API.
                                             If None, state management features will be disabled.

        """
        self.ccf_client = ccf_client

    def get_ccf_documents(self) -> CCFDocumentsMap | None:
        """
        Retrieve current document states from the Custom Connector Framework.

        Returns:
            Optional[CCFDocumentsMap]: A mapping of document IDs to their current state in CCF,
                                      or None if CCF client is not configured.

        """
        if self.ccf_client:
            return self.ccf_client.list_documents()
        return None

    def get_checkpoint(self) -> dict[str, str] | None:
        """
        Retrieve the current checkpoint data for incremental synchronization.

        Checkpoints can be used to store state between connector runs, such as
        timestamps, pagination tokens, or other synchronization metadata.

        Returns:
            Optional[Dict[str, str]]: The checkpoint data as a dictionary,
                                     or None if CCF client is not configured.

        """
        if self.ccf_client:
            return self.ccf_client.get_checkpoint()
        return None

    def save_checkpoint(self, checkpoint_data: dict[str, str]) -> None:
        """
        Save checkpoint data for future connector runs.

        Args:
            checkpoint_data (Dict[str, str]): The checkpoint data to save.
                                            This should contain any state needed for
                                            incremental synchronization.

        """
        if self.ccf_client:
            self.ccf_client.save_checkpoint(checkpoint_data)

    @abstractmethod
    def sync(self) -> None:
        """
        Synchronize documents between the source system and Amazon Q Business.

        This method orchestrates the entire synchronization process, including
        fetching documents to add/update, documents to delete, and handling
        the synchronization with Amazon Q Business.

        Implementations should handle exceptions appropriately and ensure
        proper cleanup of resources.
        """
        # pylint: disable=unnecessary-pass
        pass

    @abstractmethod
    def get_documents_to_add(self) -> Iterator[Document]:
        """
        Get documents to be added or updated in Amazon Q Business.

        This method should yield Document objects representing the content
        to be indexed in Amazon Q Business.

        Returns:
            Iterator[Document]: An iterator of Document objects to be added or updated.

        """
        # pylint: disable=unnecessary-pass
        pass

    @abstractmethod
    def get_documents_to_delete(self) -> Iterator[str]:
        """
        Get document IDs to be deleted from Amazon Q Business.

        This method should yield document IDs that should be removed from
        the Amazon Q Business index.

        Returns:
            Iterator[str]: An iterator of document IDs to be deleted.

        """
        # pylint: disable=unnecessary-pass
        pass
