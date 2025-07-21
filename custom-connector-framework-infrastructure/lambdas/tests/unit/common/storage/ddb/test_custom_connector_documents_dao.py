from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID as ACCOUNT_ID

# Imports from the Documents DAO under test
from common.storage.ddb.custom_connector_documents_dao import (
    BatchDeleteDocumentsRequest, BatchPutDocumentsRequest,
    CustomConnectorDocumentsDao, DaoInternalError, DaoResourceNotFoundError,
    DocumentItem, ListDocumentsRequest)
# Imports from CustomConnectorsDao to set up connectors for the Documents DAO
from common.storage.ddb.custom_connectors_dao import \
    ConnectorStatus as DaoConnectorStatus
from common.storage.ddb.custom_connectors_dao import (
    ContainerProperties, CreateConnectorRequest, CustomConnectorsDao,
    UpdateConnectorStatusRequest)
from common.tenant import TenantContext

CONNECTORS_TABLE = "CustomConnectors"
DOCUMENTS_TABLE = "CustomConnectorDocuments"


@pytest.fixture
def connectors_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=CONNECTORS_TABLE,
            KeySchema=[
                {"AttributeName": "custom_connector_arn_prefix", "KeyType": "HASH"},
                {"AttributeName": "connector_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "custom_connector_arn_prefix", "AttributeType": "S"},
                {"AttributeName": "connector_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        yield resource.Table(CONNECTORS_TABLE)


@pytest.fixture
def connectors_dao(connectors_table):
    return CustomConnectorsDao(connectors_table)


@pytest.fixture
def documents_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=DOCUMENTS_TABLE,
            KeySchema=[
                {"AttributeName": "custom_connector_arn_prefix", "KeyType": "HASH"},
                {"AttributeName": "document_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "custom_connector_arn_prefix", "AttributeType": "S"},
                {"AttributeName": "document_id", "AttributeType": "S"},
                {"AttributeName": "connector_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "custom_connector_arn_prefix", "KeyType": "HASH"},
                        {"AttributeName": "connector_id", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        yield resource.Table(DOCUMENTS_TABLE)


@pytest.fixture
def documents_dao(connectors_dao, documents_table):
    return CustomConnectorDocumentsDao(documents_table, connectors_dao)


@pytest.fixture
def tenant_context():
    return TenantContext(account_id=ACCOUNT_ID, region="us-east-1")


def create_sample_connector(
    connectors_dao: CustomConnectorsDao, tenant_context: TenantContext, *, in_use: bool = False
) -> str:
    """
    Helper to create a connector. By default it's AVAILABLE; set in_use=True to mark IN_USE immediately.
    Returns connector_id.
    """
    req = CreateConnectorRequest(
        tenant_context=tenant_context,
        name="doc-connector",
        description=None,
        container_properties=ContainerProperties(
            execution_role_arn="arn:role",
            image_uri="uri",
            job_role_arn="arn:job",
            environment=[],
            resource_requirements={"cpu": 1024, "memory": 2048},
            timeout=0,
        ),
    )
    resp = connectors_dao.create_connector(req)
    cid = resp.connector_id
    if in_use:
        connectors_dao.update_connector_status(
            UpdateConnectorStatusRequest(
                tenant_context=tenant_context,
                connector_id=cid,
                status=DaoConnectorStatus.IN_USE,
            )
        )
    return cid


@mock_aws
def test_batch_put_documents_connector_not_found(documents_dao, tenant_context):
    """Attempting to batch_put documents for a non-existent connector should raise DaoResourceNotFoundError."""
    bogus_req = BatchPutDocumentsRequest(
        tenant_context=tenant_context,
        connector_id="no-such-conn",
        documents=[DocumentItem(document_id="doc1", checksum="sum1")],
    )
    with pytest.raises(DaoResourceNotFoundError):
        documents_dao.batch_put_documents(bogus_req)


@mock_aws
def test_batch_put_and_verify_documents(connectors_dao, documents_dao, tenant_context):
    """
    Create a connector, mark IN_USE, then batch_put multiple documents.
    Verify documents exist in DynamoDB with correct attributes.
    """
    cid = create_sample_connector(connectors_dao, tenant_context, in_use=True)
    arn_prefix = tenant_context.get_arn_prefix()
    datetime.now(UTC).isoformat()

    docs = [
        DocumentItem(document_id="docA", checksum="csA"),
        DocumentItem(document_id="docB", checksum="csB"),
    ]
    req = BatchPutDocumentsRequest(
        tenant_context=tenant_context,
        connector_id=cid,
        documents=docs,
    )
    documents_dao.batch_put_documents(req)

    # Fetch each item directly
    for doc in docs:
        raw = documents_dao.table.get_item(
            Key={"custom_connector_arn_prefix": arn_prefix, "document_id": doc.document_id}
        ).get("Item")
        assert raw is not None
        assert raw["connector_id"] == cid
        assert raw["checksum"] == doc.checksum
        # created_at and updated_at should both appear and be ISO strings
        assert "created_at" in raw
        assert isinstance(raw["created_at"], str)
        assert "updated_at" in raw
        assert isinstance(raw["updated_at"], str)


@mock_aws
def test_batch_delete_documents_and_verify(connectors_dao, documents_dao, tenant_context):
    """
    Insert multiple documents under an IN_USE connector, then delete a subset.
    Verify only the remaining documents exist.
    """
    cid = create_sample_connector(connectors_dao, tenant_context, in_use=True)
    arn_prefix = tenant_context.get_arn_prefix()

    docs = [
        DocumentItem(document_id="docX", checksum="csX"),
        DocumentItem(document_id="docY", checksum="csY"),
        DocumentItem(document_id="docZ", checksum="csZ"),
    ]
    put_req = BatchPutDocumentsRequest(
        tenant_context=tenant_context,
        connector_id=cid,
        documents=docs,
    )
    documents_dao.batch_put_documents(put_req)

    # Delete docY and docZ
    del_req = BatchDeleteDocumentsRequest(
        tenant_context=tenant_context,
        connector_id=cid,
        document_ids=["docY", "docZ"],
    )
    documents_dao.batch_delete_documents(del_req)

    # docX should still exist
    remaining = documents_dao.table.get_item(
        Key={"custom_connector_arn_prefix": arn_prefix, "document_id": "docX"}
    ).get("Item")
    assert remaining is not None
    # docY and docZ should be gone
    assert "Item" not in documents_dao.table.get_item(
        Key={"custom_connector_arn_prefix": arn_prefix, "document_id": "docY"}
    )
    assert "Item" not in documents_dao.table.get_item(
        Key={"custom_connector_arn_prefix": arn_prefix, "document_id": "docZ"}
    )


@mock_aws
def test_list_documents_connector_not_found(documents_dao, tenant_context):
    """Listing documents for a missing connector should raise DaoResourceNotFoundError."""
    bogus_req = ListDocumentsRequest(tenant_context=tenant_context, connector_id="no-conn")
    with pytest.raises(DaoResourceNotFoundError):
        documents_dao.list_documents(bogus_req)


@mock_aws
def test_list_documents_pagination_and_invalid_token(connectors_dao, documents_dao, tenant_context):
    """
    1. Insert 5 documents under one connector → verify pagination.
    2. Insert 2 documents under a second connector → ensure they don't appear in first connector's list.
    3. Test invalid next_token raises DaoInternalError.
    """
    # Create two connectors, mark both IN_USE to allow puts
    cid1 = create_sample_connector(connectors_dao, tenant_context, in_use=True)
    cid2 = create_sample_connector(connectors_dao, tenant_context, in_use=True)
    tenant_context.get_arn_prefix()

    # Insert 5 docs under cid1
    docs_c1 = []
    for i in range(5):
        doc_id = f"c1doc{i}"
        docs_c1.append(DocumentItem(document_id=doc_id, checksum=f"cs{i}"))
    documents_dao.batch_put_documents(
        BatchPutDocumentsRequest(tenant_context=tenant_context, connector_id=cid1, documents=docs_c1)
    )

    # Insert 2 docs under cid2
    docs_c2 = [
        DocumentItem(document_id="c2doc1", checksum="csA"),
        DocumentItem(document_id="c2doc2", checksum="csB"),
    ]
    documents_dao.batch_put_documents(
        BatchPutDocumentsRequest(tenant_context=tenant_context, connector_id=cid2, documents=docs_c2)
    )

    # First page for cid1, limit=3
    page1 = documents_dao.list_documents(
        ListDocumentsRequest(tenant_context=tenant_context, connector_id=cid1, max_results=3)
    )
    assert len(page1.documents) == 3
    assert page1.next_token is not None

    # Second page should have remaining 2
    page2 = documents_dao.list_documents(
        ListDocumentsRequest(
            tenant_context=tenant_context,
            connector_id=cid1,
            max_results=3,
            next_token=page1.next_token,
        )
    )
    assert len(page2.documents) == 2
    assert page2.next_token is None

    # Ensure only documents for cid1 appear when no status filter (cid2 docs not included)
    all_ids_c1 = {
        doc.document_id
        for doc in documents_dao.list_documents(
            ListDocumentsRequest(tenant_context=tenant_context, connector_id=cid1)
        ).documents
    }
    assert {d.document_id for d in docs_c1} == all_ids_c1

    # Invalid next_token should raise DaoInternalError
    with pytest.raises(DaoInternalError):
        documents_dao.list_documents(
            ListDocumentsRequest(tenant_context=tenant_context, connector_id=cid1, next_token="not a json")
        )
