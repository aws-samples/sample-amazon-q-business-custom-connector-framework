"""
Document models for the Amazon Q Business Custom Connector Framework.

This module defines the core document models used to represent files and their metadata
for indexing in Amazon Q Business. These models handle content type detection, file access,
and checksum calculation for change detection.
"""

import hashlib
import json
import mimetypes
from datetime import UTC, datetime
from pathlib import Path

import filetype
from pydantic import BaseModel, ConfigDict, Field

from custom_connector_framework.models.exceptions import UnsupportedDocumentError
from custom_connector_framework.models.qbusiness import AccessControl
from custom_connector_framework.types import ContentType, DocumentTypeMapper


class DocumentMetadata(BaseModel):
    """
    Metadata for a document including access controls and attributes.

    This class represents all metadata associated with a document, including
    title, source URI, timestamps, custom attributes, and access controls.

    Attributes:
        title (str): The document title.
        source_uri (Optional[str]): The source URI of the document.
        last_updated_at (str): ISO-formatted timestamp of when the document was last updated.
        created_at (str): ISO-formatted timestamp of when the document was created.
        attributes (Dict[str, str]): Custom attributes for the document.
        access_control_list (List[AccessControl]): Access control configurations for the document.

    """

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
        from_attributes=True,
    )
    title: str
    source_uri: str | None = None
    last_updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    attributes: dict[str, str] = Field(default_factory=dict)
    access_control_list: list[AccessControl] = Field(default_factory=list)


class DocumentFile:
    """
    Represents a file on the local filesystem with methods for content access and type detection.

    This class handles file operations such as reading content, determining file size,
    and inferring content type based on file characteristics.

    Attributes:
        file_path (Path): Path to the file on the local filesystem.

    """

    def __init__(self, file_path: str | Path):
        """
        Initialize a DocumentFile instance.

        Args:
            file_path (Union[str, Path]): Path to the file on the local filesystem.

        Raises:
            FileNotFoundError: If the specified file does not exist.

        """
        self.file_path = Path(file_path) if isinstance(file_path, str) else file_path
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

    def infer_content_type(self) -> ContentType:
        """
        Determine the content type of the file.

        This method uses multiple strategies to determine the content type:
        1. First tries using the filetype library for binary detection
        2. Falls back to mimetypes based on file extension
        3. Finally tries to determine type from extension directly

        Returns:
            ContentType: The detected content type enum value.

        Raises:
            UnsupportedDocumentError: If the content type cannot be determined or is not supported.

        """
        try:
            # Try to detect content type using filetype library (works best for binary files)
            kind = filetype.guess(str(self.file_path))
            if kind:
                mime_type = kind.mime
            else:
                # Fall back to mimetypes based on extension
                mime_type, _ = mimetypes.guess_type(str(self.file_path))
                if not mime_type:
                    # Last resort: try to determine from extension directly
                    extension = self.file_path.suffix.lower().lstrip(".")
                    return DocumentTypeMapper.get_content_type_from_extension(extension)

            try:
                return DocumentTypeMapper.get_content_type_from_mime(mime_type)
            except UnsupportedDocumentError:
                # If mime type lookup fails, try extension-based lookup
                extension = self.file_path.suffix.lower().lstrip(".")
                return DocumentTypeMapper.get_content_type_from_extension(extension)

        except (UnsupportedDocumentError, ValueError) as error:
            raise UnsupportedDocumentError(f"Unable to determine content type for file: {self.file_path}") from error

    def read_content(self) -> str:
        """
        Read the content of the file as text.

        This method is only supported for text-based file types.

        Returns:
            str: The content of the file as a string.

        Raises:
            NotImplementedError: If the file type is not supported for text reading.

        """
        content_type = self.infer_content_type()
        # Only attempt to read text-based file types
        if content_type in {
            ContentType.HTML,
            ContentType.XML,
            ContentType.XSLT,
            ContentType.MD,
            ContentType.JSON,
            ContentType.CSV,
            ContentType.PLAIN_TEXT,
        }:
            with open(self.file_path, encoding="utf-8") as file_handle:
                return file_handle.read()
        raise NotImplementedError(f"Content extraction not implemented for {content_type.value} files.")

    def get_size(self) -> int:
        """
        Get the size of the file in bytes.

        Returns:
            int: The size of the file in bytes.

        """
        return self.file_path.stat().st_size


class Document(BaseModel):
    """
    Base document model that combines file content and metadata.

    This class represents a complete document to be indexed in Amazon Q Business,
    including its unique identifier, file content, and associated metadata.

    Attributes:
        id (str): The unique identifier for the document in Amazon Q Business.
        file (DocumentFile): The file content to be indexed.
        metadata (DocumentMetadata): Metadata associated with the document.

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    file: DocumentFile
    metadata: DocumentMetadata

    def get_checksum(self) -> str:
        """
        Calculate a document checksum including content and metadata.

        This method generates a SHA-256 hash that incorporates both the document's
        metadata and file content, allowing for efficient change detection.

        The checksum excludes timestamps to avoid unnecessary updates when only
        the timestamps have changed.

        Returns:
            str: SHA-256 hash of document content and metadata.

        """
        # Use pydantic's model_dump_json to handle complex object serialization,
        # then normalize the JSON for consistent hashing by sorting keys
        metadata = json.dumps(
            json.loads(self.metadata.model_dump_json(exclude={"last_updated_at", "created_at"}, exclude_none=True)),
            sort_keys=True,
        )
        data = f"{self.id}+{metadata}"

        # Add file content hash to the checksum calculation
        with open(self.file.file_path, "rb") as file_handle:
            data += f"+{hashlib.sha256(file_handle.read()).hexdigest()}"

        return hashlib.sha256(data.encode()).hexdigest()
