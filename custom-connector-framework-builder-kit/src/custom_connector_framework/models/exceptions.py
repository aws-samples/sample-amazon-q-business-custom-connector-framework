"""
Exception classes for the Custom Connector Framework.

This module defines custom exceptions used throughout the framework
to provide clear error handling and reporting.
"""


class DocumentError(Exception):
    """
    Base class for document-related errors.

    This exception serves as the parent class for all document-specific
    exceptions in the framework.
    """

    # pylint: disable=unnecessary-pass
    pass


class UnsupportedDocumentError(DocumentError):
    """
    Raised when a document type is not supported.

    This exception is raised when attempting to process a document with
    an unsupported file format, extension, or MIME type.
    """

    # pylint: disable=unnecessary-pass
    pass


class S3UploadError(Exception):
    """
    Raised when an S3 upload operation fails.

    This exception is raised when a document cannot be uploaded to S3,
    which may occur due to permissions issues, network problems, or
    invalid document content.
    """

    # pylint: disable=unnecessary-pass
    pass


class S3DeleteError(Exception):
    """
    Raised when an S3 delete operation fails.

    This exception is raised when a document cannot be deleted from S3,
    which may occur due to permissions issues or if the object doesn't exist.
    """

    # pylint: disable=unnecessary-pass
    pass
