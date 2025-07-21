import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.stub import Stubber

from custom_connector_framework.ccf_client import CCFClient
from custom_connector_framework.custom_connector_interface import \
    QBusinessCustomConnectorInterface
from custom_connector_framework.models.document import (
    Document, DocumentFile, DocumentMetadata, UnsupportedDocumentError)
from custom_connector_framework.models.qbusiness import (
    AccessConfiguration, AccessControl, AccessType, BatchPutDocumentRequest,
    DocumentAttribute, DocumentContent, MemberRelation, MembershipType,
    Principal, PrincipalGroup, PrincipalUser, QBusinessDocument, Value)
from custom_connector_framework.utils import JsonSerializer


class TestQBusinessConnector(QBusinessCustomConnectorInterface):
    """Test implementation of QBusinessCustomConnectorInterface."""

    _documents_to_add = []
    _documents_to_delete = []

    def get_documents_to_add(self) -> Iterator[Document]:
        return iter(self._documents_to_add)

    def get_documents_to_delete(self) -> Iterator[str]:
        return iter(self._documents_to_delete)

    def set_documents_to_add(self, documents):
        self._documents_to_add = documents

    def set_documents_to_delete(self, document_ids):
        self._documents_to_delete = document_ids


@pytest.fixture
def test_ids():
    return {
        "application_id": str(uuid.uuid4()),
        "index_id": str(uuid.uuid4()),
        "data_source_id": str(uuid.uuid4()),
    }


@pytest.fixture
def execution_id():
    return str(uuid.uuid4())


@pytest.fixture
def sample_principals():
    return [
        Principal(
            user=PrincipalUser(access=AccessType.ALLOW, id="user@example.com", membershipType=MembershipType.INDEX)
        ),
        Principal(
            group=PrincipalGroup(access=AccessType.ALLOW, name="engineering-group", membershipType=MembershipType.INDEX)
        ),
        Principal(
            group=PrincipalGroup(access=AccessType.DENY, name="restricted-group", membershipType=MembershipType.INDEX)
        ),
    ]


@pytest.fixture
def mock_qbusiness_client():
    client = boto3.client("qbusiness", region_name="us-east-1")
    stubber = Stubber(client)
    return client, stubber


@pytest.fixture
def mock_s3_client():
    client = boto3.client("s3", region_name="us-east-1")
    stubber = Stubber(client)
    return client, stubber


@pytest.fixture
def sample_text_file():
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("Test content")
    file_path = Path(f.name)
    yield file_path
    file_path.unlink()


@pytest.fixture
def large_text_file():
    # Create a file larger than 10MB but smaller than 50MB
    size = 15 * 1024 * 1024  # 15MB
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="wb", delete=False) as f:
        f.write(b"0" * size)
    file_path = Path(f.name)
    yield file_path
    file_path.unlink()


@pytest.fixture
def connector(mock_qbusiness_client, mock_s3_client, test_ids):
    client, stubber = mock_qbusiness_client
    s3_client, s3_stubber = mock_s3_client

    connector = TestQBusinessConnector(
        qbusiness_client=client,
        qbusiness_app_id=test_ids["application_id"],
        qbusiness_index_id=test_ids["index_id"],
        qbusiness_data_source_id=test_ids["data_source_id"],
        s3_client=s3_client,
        s3_bucket="test-bucket",
    )

    return connector, stubber, s3_stubber, test_ids


@pytest.fixture
def mock_ccf_client():
    """Mock CCF client since the service definition is only available after deployment."""
    # Create a mock boto3 client that doesn't require the actual CCF service
    mock_client = MagicMock()

    # Create a stubber-like object for consistency with other tests
    class MockStubber:
        def __init__(self, client):
            self.client = client
            self._responses = []
            self._current_response = 0

        def add_response(self, operation_name, response, expected_params=None):
            self._responses.append(
                {"operation": operation_name, "response": response, "expected_params": expected_params}
            )

        def __enter__(self):
            # Set up the mock client to return responses in order
            def create_side_effect(operation):
                def side_effect(*args, **kwargs):
                    for resp in self._responses:
                        if resp["operation"] == operation:
                            return resp["response"]
                    return {}

                return side_effect

            # Mock the specific operations used in tests
            mock_client.list_custom_connector_documents = MagicMock(
                side_effect=create_side_effect("list_custom_connector_documents")
            )
            mock_client.batch_put_custom_connector_documents = MagicMock(
                side_effect=create_side_effect("batch_put_custom_connector_documents")
            )
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    stubber = MockStubber(mock_client)
    return mock_client, stubber


def test_when_small_file_uploaded_then_inline_content_used(
    connector, sample_text_file, execution_id, sample_principals
):
    connector_instance, stubber, _, test_ids = connector

    access_controls = [AccessControl(memberRelation=MemberRelation.AND, principals=[sample_principals[0]])]

    metadata = DocumentMetadata(title="Test Document", access_control_list=access_controls)
    doc = Document(id="test-doc", file=DocumentFile(sample_text_file), metadata=metadata)
    connector_instance.set_documents_to_add([doc])

    # 1. Start sync job
    stubber.add_response(
        "start_data_source_sync_job",
        {"executionId": execution_id},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    # 2. Batch put document
    with open(sample_text_file, "rb") as f:
        content = f.read()

    qbusiness_doc = QBusinessDocument(
        id="test-doc",
        title="Test Document",
        contentType="PLAIN_TEXT",
        content=DocumentContent(blob=content),
        attributes=[
            DocumentAttribute(name="_last_updated_at", value=Value(stringValue=metadata.last_updated_at)),
            DocumentAttribute(name="_created_at", value=Value(stringValue=metadata.created_at)),
        ],
        accessConfiguration=AccessConfiguration(accessControls=access_controls, memberRelation=MemberRelation.AND),
    )

    request = BatchPutDocumentRequest(
        applicationId=test_ids["application_id"],
        indexId=test_ids["index_id"],
        documents=[qbusiness_doc],
        dataSourceSyncId=execution_id,
    )

    expected_request = JsonSerializer.serialize(request.model_dump(exclude_none=True))

    # 3. Stop sync job
    stubber.add_response(
        "stop_data_source_sync_job",
        {},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    # 4. Add batch put document response last
    stubber.add_response("batch_put_document", {"failedDocuments": []}, expected_request)

    with stubber:
        connector_instance.sync()


def test_when_large_file_uploaded_then_s3_content_used(connector, large_text_file, execution_id, sample_principals):
    connector_instance, stubber, s3_stubber, test_ids = connector

    access_controls = [AccessControl(memberRelation=MemberRelation.AND, principals=[sample_principals[0]])]

    metadata = DocumentMetadata(title="Large Document", access_control_list=access_controls)
    doc = Document(id="large-doc", file=DocumentFile(large_text_file), metadata=metadata)
    connector_instance.set_documents_to_add([doc])

    # 1. Start sync job
    stubber.add_response(
        "start_data_source_sync_job",
        {"executionId": execution_id},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    # 2. S3 upload
    s3_key = f"qbusiness-docs/large-doc{large_text_file.suffix}"
    with open(large_text_file, "rb") as f:
        content = f.read()
        s3_stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": "test-bucket",
                "Key": s3_key,
                "Body": content,
            },
        )

    # 3. Create request with S3 reference
    qbusiness_doc = QBusinessDocument(
        id="large-doc",
        title="Large Document",
        contentType="PLAIN_TEXT",
        content=DocumentContent(s3={"bucket": "test-bucket", "key": s3_key}),
        attributes=[
            DocumentAttribute(name="_last_updated_at", value=Value(stringValue=metadata.last_updated_at)),
            DocumentAttribute(name="_created_at", value=Value(stringValue=metadata.created_at)),
        ],
        accessConfiguration=AccessConfiguration(accessControls=access_controls, memberRelation=MemberRelation.AND),
    )

    request = BatchPutDocumentRequest(
        applicationId=test_ids["application_id"],
        indexId=test_ids["index_id"],
        documents=[qbusiness_doc],
        dataSourceSyncId=execution_id,
    )

    expected_request = JsonSerializer.serialize(request.model_dump(exclude_none=True))

    # 4. Stop sync job
    stubber.add_response(
        "stop_data_source_sync_job",
        {},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    # 5. Batch put document
    stubber.add_response("batch_put_document", {"failedDocuments": []}, expected_request)

    with stubber, s3_stubber:
        connector_instance.sync()


def test_when_documents_deleted_then_batch_delete_called(connector, execution_id):
    connector_instance, stubber, _, test_ids = connector

    doc_ids = ["doc1", "doc2", "doc3"]
    connector_instance.set_documents_to_delete(doc_ids)

    # 1. Start sync job
    stubber.add_response(
        "start_data_source_sync_job",
        {"executionId": execution_id},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    # 2. Batch delete
    request = {
        "applicationId": test_ids["application_id"],
        "indexId": test_ids["index_id"],
        "documents": [{"documentId": doc_id} for doc_id in doc_ids],
        "dataSourceSyncId": execution_id,
    }

    stubber.add_response("batch_delete_document", {"failedDocuments": []}, request)

    # 3. Stop sync job
    stubber.add_response(
        "stop_data_source_sync_job",
        {},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    with stubber:
        connector_instance.sync()


def test_when_sync_fails_then_exception_raised(connector, sample_text_file, execution_id):
    connector_instance, stubber, _, test_ids = connector

    metadata = DocumentMetadata(title="Test Document")
    doc = Document(id="test-doc", file=DocumentFile(sample_text_file), metadata=metadata)
    connector_instance.set_documents_to_add([doc])

    # 1. Start sync job - simulate failure
    stubber.add_client_error(
        "start_data_source_sync_job",
        service_error_code="InvalidParameterException",
        service_message="Invalid parameter",
    )

    with stubber, pytest.raises(Exception):
        connector_instance.sync()


def test_when_document_type_unsupported_then_error_raised(connector, execution_id):
    connector_instance, stubber, _, test_ids = connector

    # Create a temporary file with unsupported extension
    with tempfile.NamedTemporaryFile(suffix=".xyz", mode="w", delete=False) as f:
        f.write("Test content")
    unsupported_file = Path(f.name)

    try:
        metadata = DocumentMetadata(title="Unsupported Document")
        doc = Document(id="unsupported-doc", file=DocumentFile(unsupported_file), metadata=metadata)
        connector_instance.set_documents_to_add([doc])

        # Add start sync job response
        stubber.add_response(
            "start_data_source_sync_job",
            {"executionId": execution_id},
            {
                "applicationId": test_ids["application_id"],
                "indexId": test_ids["index_id"],
                "dataSourceId": test_ids["data_source_id"],
            },
        )

        # Add stop sync job response since it will be called in the finally block
        stubber.add_response(
            "stop_data_source_sync_job",
            {},
            {
                "applicationId": test_ids["application_id"],
                "indexId": test_ids["index_id"],
                "dataSourceId": test_ids["data_source_id"],
            },
        )

        with stubber:
            with pytest.raises(UnsupportedDocumentError) as exc_info:
                connector_instance.sync()
            assert "Unable to determine content type for file" in str(exc_info.value)

    finally:
        # Clean up the temporary file
        if unsupported_file.exists():
            unsupported_file.unlink()


@pytest.mark.ccf_required
def test_when_ccf_enabled_checksums_used_for_sync(
    connector, sample_text_file, execution_id, sample_principals, mock_ccf_client
):
    """Test that CCF checksums are used to determine which documents need syncing."""
    connector_instance, stubber, _, test_ids = connector
    ccf_client, ccf_stubber = mock_ccf_client

    # Create CCF client and add it to connector
    ccf_docs_client = CCFClient(ccf_client, "test-connector-id")
    connector_instance.ccf_client = ccf_docs_client

    # Create test document
    access_controls = [AccessControl(memberRelation=MemberRelation.AND, principals=[sample_principals[0]])]
    metadata = DocumentMetadata(title="Test Document", access_control_list=access_controls)
    doc = Document(id="test-doc", file=DocumentFile(sample_text_file), metadata=metadata)
    connector_instance.set_documents_to_add([doc])

    # Calculate expected checksum
    expected_checksum = doc.get_checksum()

    # Setup CCF list documents response
    ccf_stubber.add_response(
        "list_custom_connector_documents",
        {"documents": []},  # Empty list means no existing documents, omit next_token
        {"connector_id": "test-connector-id"},
    )

    # Setup CCF batch put documents response
    ccf_stubber.add_response(
        "batch_put_custom_connector_documents",
        {},
        {
            "connector_id": "test-connector-id",
            "documents": [{"document_id": "test-doc", "checksum": expected_checksum}],
        },
    )

    # Setup Q Business responses
    stubber.add_response(
        "start_data_source_sync_job",
        {"executionId": execution_id},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    # Add batch put document response
    with open(sample_text_file, "rb") as f:
        content = f.read()

    qbusiness_doc = QBusinessDocument(
        id="test-doc",
        title="Test Document",
        contentType="PLAIN_TEXT",
        content=DocumentContent(blob=content),
        attributes=[
            DocumentAttribute(name="_last_updated_at", value=Value(stringValue=metadata.last_updated_at)),
            DocumentAttribute(name="_created_at", value=Value(stringValue=metadata.created_at)),
        ],
        accessConfiguration=AccessConfiguration(accessControls=access_controls, memberRelation=MemberRelation.AND),
    )

    request = BatchPutDocumentRequest(
        applicationId=test_ids["application_id"],
        indexId=test_ids["index_id"],
        documents=[qbusiness_doc],
        dataSourceSyncId=execution_id,
    )

    expected_request = JsonSerializer.serialize(request.model_dump(exclude_none=True))

    # Stop sync job must be added before batch_put_document because of finally block
    stubber.add_response(
        "stop_data_source_sync_job",
        {},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    stubber.add_response("batch_put_document", {"failedDocuments": []}, expected_request)

    with stubber, ccf_stubber:
        connector_instance.sync()


@pytest.mark.ccf_required
def test_when_document_unchanged_then_skip_sync(
    connector, sample_text_file, execution_id, sample_principals, mock_ccf_client
):
    """Test that documents with unchanged checksums are skipped."""
    connector_instance, stubber, _, test_ids = connector
    ccf_client, ccf_stubber = mock_ccf_client

    # Create CCF client and add it to connector
    ccf_docs_client = CCFClient(ccf_client, "test-connector-id")
    connector_instance.ccf_client = ccf_docs_client

    # Create test document
    access_controls = [AccessControl(memberRelation=MemberRelation.AND, principals=[sample_principals[0]])]
    metadata = DocumentMetadata(title="Test Document", access_control_list=access_controls)
    doc = Document(id="test-doc", file=DocumentFile(sample_text_file), metadata=metadata)
    connector_instance.set_documents_to_add([doc])

    # Calculate checksum
    checksum = doc.get_checksum()

    # Setup CCF list documents response with matching checksum
    ccf_stubber.add_response(
        "list_custom_connector_documents",
        {
            "documents": [
                {
                    "document_id": "test-doc",
                    "checksum": checksum,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
            ]
        },
        {"connector_id": "test-connector-id"},
    )

    # Setup Q Business responses - only start/stop since no sync needed
    stubber.add_response(
        "start_data_source_sync_job",
        {"executionId": execution_id},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    stubber.add_response(
        "stop_data_source_sync_job",
        {},
        {
            "applicationId": test_ids["application_id"],
            "indexId": test_ids["index_id"],
            "dataSourceId": test_ids["data_source_id"],
        },
    )

    with stubber, ccf_stubber:
        connector_instance.sync()
