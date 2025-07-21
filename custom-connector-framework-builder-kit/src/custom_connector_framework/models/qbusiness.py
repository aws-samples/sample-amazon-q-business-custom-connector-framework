"""Amazon Q Business data models for interacting with the Q Business API."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ValueType(str, Enum):
    """Enumeration of value types for document attributes."""

    STRING_VALUE = "stringValue"
    LONG_VALUE = "longValue"
    STRING_LIST_VALUE = "stringListValue"


class Operator(str, Enum):
    """Enumeration of operators for document conditions."""

    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUALS = "GREATER_THAN_OR_EQUALS"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUALS = "LESS_THAN_OR_EQUALS"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"


class DocumentContentOperator(str, Enum):
    """Enumeration of document content operators for enrichment."""

    DELETE = "DELETE"
    REDACT = "REDACT"


class AttributeValueOperator(str, Enum):
    """Enumeration of attribute value operators for document enrichment."""

    REPLACE = "REPLACE"
    DELETE = "DELETE"


class MembershipType(str, Enum):
    """Membership type for principals."""

    INDEX = "INDEX"
    DATASOURCE = "DATASOURCE"


class AccessType(str, Enum):
    """Access type for principals."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class MemberRelation(str, Enum):
    """Enumeration of member relations for access control."""

    AND = "AND"
    OR = "OR"


class MediaExtractionStatus(str, Enum):
    """Enumeration of media extraction status values."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class PrincipalUser(BaseModel):
    """User principal model for access control."""

    model_config = ConfigDict(extra="forbid")
    access: AccessType
    id: str | None = None
    membership_type: MembershipType | None = Field(None, alias="membershipType")


class PrincipalGroup(BaseModel):
    """Group principal model for access control."""

    model_config = ConfigDict(extra="forbid")
    access: AccessType
    name: str | None = None
    membership_type: MembershipType | None = Field(None, alias="membershipType")


class Principal(BaseModel):
    """Principal model for access control, can be either user or group."""

    model_config = ConfigDict(extra="forbid")
    user: PrincipalUser | None = None
    group: PrincipalGroup | None = None


class AccessControl(BaseModel):
    """Access control configuration for documents."""

    member_relation: MemberRelation = Field(alias="memberRelation")
    principals: list[Principal]


class Value(BaseModel):
    """Value model for document attributes."""

    model_config = ConfigDict(extra="forbid")
    string_value: str | None = Field(None, alias="stringValue")
    long_value: int | None = Field(None, alias="longValue")
    string_list_value: list[str] | None = Field(None, alias="stringListValue")


class Condition(BaseModel):
    """Condition model for document enrichment rules."""

    key: str
    operator: Operator
    value: Value


class Target(BaseModel):
    """Target model for document enrichment operations."""

    key: str
    attribute_value_operator: AttributeValueOperator = Field(alias="attributeValueOperator")
    value: Value | None = None


class InlineConfiguration(BaseModel):
    """Inline configuration for document enrichment."""

    condition: Condition
    document_content_operator: DocumentContentOperator = Field(alias="documentContentOperator")
    target: Target


class HookConfiguration(BaseModel):
    """Hook configuration for document processing."""

    invocation_condition: Condition | None = Field(None, alias="invocationCondition")
    lambda_arn: str = Field(alias="lambdaArn")
    role_arn: str = Field(alias="roleArn")
    s3_bucket_name: str = Field(alias="s3BucketName")


class DocumentEnrichmentConfiguration(BaseModel):
    """Document enrichment configuration."""

    inline_configurations: list[InlineConfiguration] | None = Field(None, alias="inlineConfigurations")
    pre_extraction_hook_configuration: HookConfiguration | None = Field(None, alias="preExtractionHookConfiguration")
    post_extraction_hook_configuration: HookConfiguration | None = Field(None, alias="postExtractionHookConfiguration")


class AudioExtractionConfiguration(BaseModel):
    """Audio extraction configuration for media processing."""

    audio_extraction_status: MediaExtractionStatus = Field(alias="audioExtractionStatus")


class ImageExtractionConfiguration(BaseModel):
    """Image extraction configuration for media processing."""

    image_extraction_status: MediaExtractionStatus = Field(alias="imageExtractionStatus")


class VideoExtractionConfiguration(BaseModel):
    """Video extraction configuration for media processing."""

    video_extraction_status: MediaExtractionStatus = Field(alias="videoExtractionStatus")


class MediaExtractionConfiguration(BaseModel):
    """Media extraction configuration for processing audio, image, and video content."""

    audio_extraction_configuration: AudioExtractionConfiguration | None = Field(
        None, alias="audioExtractionConfiguration"
    )
    image_extraction_configuration: ImageExtractionConfiguration | None = Field(
        None, alias="imageExtractionConfiguration"
    )
    video_extraction_configuration: VideoExtractionConfiguration | None = Field(
        None, alias="videoExtractionConfiguration"
    )


class AccessConfiguration(BaseModel):
    """Access configuration for document permissions."""

    access_controls: list[AccessControl] = Field(alias="accessControls")
    member_relation: Optional["MemberRelation"] = Field(None, alias="memberRelation")


class DocumentAttribute(BaseModel):
    """Document attribute model for metadata."""

    name: str
    value: Value


class S3(BaseModel):
    """S3 location model for document storage."""

    bucket: str
    key: str


class DocumentContent(BaseModel):
    """Document content model for Q Business API."""

    model_config = ConfigDict(extra="forbid")
    blob: bytes | None = None
    s3: S3 | None = None  # pylint: disable=invalid-name

    def __init__(self, **data):
        super().__init__(**data)
        if bool(self.blob) == bool(self.s3):
            raise ValueError("Exactly one of 'blob' or 's3' must be provided")


class QBusinessDocument(BaseModel):
    """Q Business document model for API operations."""

    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    content_type: str = Field(alias="contentType")
    content: DocumentContent
    attributes: list[DocumentAttribute] = Field(default_factory=list)
    access_configuration: AccessConfiguration | None = Field(None, alias="accessConfiguration")
    document_enrichment_configuration: DocumentEnrichmentConfiguration | None = Field(
        None, alias="documentEnrichmentConfiguration"
    )
    media_extraction_configuration: MediaExtractionConfiguration | None = Field(
        None, alias="mediaExtractionConfiguration"
    )


class FailedDocument(BaseModel):
    """Failed document model for batch operation responses."""

    error_code: str = Field(alias="errorCode")
    error_message: str = Field(alias="errorMessage")
    id: str


class BatchPutDocumentRequest(BaseModel):
    """Batch put document request model."""

    model_config = ConfigDict(extra="forbid")
    application_id: str = Field(alias="applicationId")
    index_id: str = Field(alias="indexId")
    documents: list[QBusinessDocument]
    data_source_sync_id: str = Field(alias="dataSourceSyncId")
    role_arn: str | None = Field(None, alias="roleArn")


class BatchPutDocumentResponse(BaseModel):
    """Batch put document response model."""

    failed_documents: list[FailedDocument] = Field(default_factory=list, alias="failedDocuments")


class DocumentToDelete(BaseModel):
    """Document to delete model for batch operations."""

    document_id: str = Field(alias="documentId")


class BatchDeleteDocumentRequest(BaseModel):
    """Batch delete document request model."""

    application_id: str = Field(alias="applicationId")
    index_id: str = Field(alias="indexId")
    documents: list[DocumentToDelete]
    data_source_sync_id: str = Field(alias="dataSourceSyncId")
    role_arn: str | None = Field(None, alias="roleArn")


class BatchDeleteDocumentResponse(BaseModel):
    """Batch delete document response model."""

    failed_documents: list[FailedDocument] = Field(default_factory=list, alias="failedDocuments")
