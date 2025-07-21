"""
Type definitions for document content types and format mappings.

This module defines enumerations for content types, file extensions, and MIME types,
along with mapping utilities to convert between them. These types are used for
document content type detection and validation.
"""

from enum import Enum
from typing import ClassVar

from custom_connector_framework.models.exceptions import UnsupportedDocumentError


class ContentType(str, Enum):
    """
    Enumeration of supported content types in Amazon Q Business.

    These values represent the standardized content types used when
    indexing documents in Amazon Q Business.
    """

    PDF = "PDF"
    HTML = "HTML"
    XML = "XML"
    XSLT = "XSLT"
    MD = "MD"
    CSV = "CSV"
    MS_EXCEL = "MS_EXCEL"
    JSON = "JSON"
    RTF = "RTF"
    PPT = "PPT"
    MS_WORD = "MS_WORD"
    PLAIN_TEXT = "PLAIN_TEXT"


class FileExtension(str, Enum):
    """
    Enumeration of supported file extensions.

    These values represent the file extensions that can be mapped
    to content types for document processing.
    """

    PDF = "pdf"
    HTML = "html"
    HTM = "htm"
    XML = "xml"
    XSLT = "xslt"
    XSL = "xsl"
    MD = "md"
    MARKDOWN = "markdown"
    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"
    JSON = "json"
    RTF = "rtf"
    PPTX = "pptx"
    PPT = "ppt"
    DOCX = "docx"
    DOC = "doc"
    TXT = "txt"


class MimeType(str, Enum):
    """
    Enumeration of supported MIME types.

    These values represent the MIME types that can be mapped
    to content types for document processing.
    """

    PDF = "application/pdf"
    HTML = "text/html"
    HTML_APP = "application/html"
    XML = "text/xml"
    XML_APP = "application/xml"
    XSLT = "application/xslt+xml"
    MARKDOWN = "text/markdown"
    MARKDOWN_X = "text/x-markdown"
    CSV = "text/csv"
    CSV_APP = "application/csv"
    EXCEL = "application/vnd.ms-excel"
    EXCEL_OPENXML = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    JSON = "application/json"
    RTF = "application/rtf"
    RTF_TEXT = "text/rtf"
    POWERPOINT = "application/vnd.ms-powerpoint"
    POWERPOINT_OPENXML = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    WORD = "application/msword"
    WORD_OPENXML = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    PLAIN_TEXT = "text/plain"


class DocumentTypeMapper:
    """
    Utility class for mapping between file extensions, MIME types, and content types.

    This class provides static mapping tables and methods to convert from file extensions
    or MIME types to the standardized ContentType enumeration used by Amazon Q Business.
    """

    # Mapping from file extensions to content types
    EXTENSION_TO_CONTENT_TYPE: ClassVar[dict[FileExtension, ContentType]] = {
        FileExtension.PDF: ContentType.PDF,
        FileExtension.HTML: ContentType.HTML,
        FileExtension.HTM: ContentType.HTML,
        FileExtension.XML: ContentType.XML,
        FileExtension.XSLT: ContentType.XSLT,
        FileExtension.XSL: ContentType.XSLT,
        FileExtension.MD: ContentType.MD,
        FileExtension.MARKDOWN: ContentType.MD,
        FileExtension.CSV: ContentType.CSV,
        FileExtension.XLSX: ContentType.MS_EXCEL,
        FileExtension.XLS: ContentType.MS_EXCEL,
        FileExtension.JSON: ContentType.JSON,
        FileExtension.RTF: ContentType.RTF,
        FileExtension.PPTX: ContentType.PPT,
        FileExtension.PPT: ContentType.PPT,
        FileExtension.DOCX: ContentType.MS_WORD,
        FileExtension.DOC: ContentType.MS_WORD,
        FileExtension.TXT: ContentType.PLAIN_TEXT,
    }

    # Mapping from MIME types to content types
    MIME_TO_CONTENT_TYPE: ClassVar[dict[MimeType, ContentType]] = {
        MimeType.PDF: ContentType.PDF,
        MimeType.HTML: ContentType.HTML,
        MimeType.HTML_APP: ContentType.HTML,
        MimeType.XML: ContentType.XML,
        MimeType.XML_APP: ContentType.XML,
        MimeType.XSLT: ContentType.XSLT,
        MimeType.MARKDOWN: ContentType.MD,
        MimeType.MARKDOWN_X: ContentType.MD,
        MimeType.CSV: ContentType.CSV,
        MimeType.CSV_APP: ContentType.CSV,
        MimeType.EXCEL: ContentType.MS_EXCEL,
        MimeType.EXCEL_OPENXML: ContentType.MS_EXCEL,
        MimeType.JSON: ContentType.JSON,
        MimeType.RTF: ContentType.RTF,
        MimeType.RTF_TEXT: ContentType.RTF,
        MimeType.POWERPOINT: ContentType.PPT,
        MimeType.POWERPOINT_OPENXML: ContentType.PPT,
        MimeType.WORD: ContentType.MS_WORD,
        MimeType.WORD_OPENXML: ContentType.MS_WORD,
        MimeType.PLAIN_TEXT: ContentType.PLAIN_TEXT,
    }

    @classmethod
    def get_content_type_from_extension(cls, extension: str) -> ContentType:
        """
        Convert a file extension to a ContentType.

        Args:
            extension (str): The file extension (with or without leading dot)

        Returns:
            ContentType: The corresponding content type

        Raises:
            UnsupportedDocumentError: If the extension is not supported

        """
        try:
            file_ext = FileExtension(extension.lower().lstrip("."))
            return cls.EXTENSION_TO_CONTENT_TYPE[file_ext]
        except (ValueError, KeyError) as error:
            raise UnsupportedDocumentError(f"Unsupported file extension: {extension}") from error

    @classmethod
    def get_content_type_from_mime(cls, mime_type: str) -> ContentType:
        """
        Convert a MIME type to a ContentType.

        Args:
            mime_type (str): The MIME type string

        Returns:
            ContentType: The corresponding content type

        Raises:
            UnsupportedDocumentError: If the MIME type is not supported

        """
        try:
            mime = MimeType(mime_type.lower())
            return cls.MIME_TO_CONTENT_TYPE[mime]
        except (ValueError, KeyError) as error:
            raise UnsupportedDocumentError(f"Unsupported MIME type: {mime_type}") from error
