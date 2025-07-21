import boto3
import pytest
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID as ACCOUNT_ID

from common.storage.ddb.custom_connectors_dao import \
    ResourceRequirements  # NEW
from common.storage.ddb.custom_connectors_dao import (
    ConnectorStatus, ContainerProperties, CreateConnectorRequest,
    CreateConnectorResponse, CustomConnectorsDao, DaoConflictError,
    DaoResourceNotFoundError, DeleteCheckpointRequest, DeleteConnectorRequest,
    GetCheckpointRequest, GetCheckpointResponse, GetConnectorRequest,
    GetConnectorResponse, ListConnectorsRequest, ListConnectorsResponse,
    PutCheckpointRequest, UpdateConnectorStatusRequest)
from common.tenant import TenantContext

TABLE_NAME = "CustomConnectors"


@pytest.fixture
def dynamodb_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE_NAME,
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
        table = resource.Table(TABLE_NAME)
        yield table


@pytest.fixture
def dao(dynamodb_table):
    return CustomConnectorsDao(dynamodb_table)


@pytest.fixture
def tenant_context():
    return TenantContext(account_id=ACCOUNT_ID, region="us-east-1")


@mock_aws
def test_create_and_get_connector(dynamodb_table, dao, tenant_context):
    # Build ContainerProperties with new ResourceRequirements
    container_props = ContainerProperties(
        execution_role_arn="arn:role",
        image_uri="uri",
        job_role_arn="arn:job",
        environment=[],  # still a list
        resource_requirements=ResourceRequirements(cpu=1024, memory=2048),
        timeout=0,
    )

    req = CreateConnectorRequest(
        tenant_context=tenant_context,
        name="test-conn",
        description="desc",
        container_properties=container_props,
    )

    resp: CreateConnectorResponse = dao.create_connector(req)
    assert resp.connector_id.startswith("cc-")
    assert resp.name == "test-conn"
    assert resp.status == ConnectorStatus.AVAILABLE

    get_req = GetConnectorRequest(
        tenant_context=tenant_context,
        connector_id=resp.connector_id,
    )
    fetched: GetConnectorResponse = dao.get_connector(get_req)
    assert fetched.connector_id == resp.connector_id
    assert fetched.name == "test-conn"
    assert fetched.status == ConnectorStatus.AVAILABLE
    assert fetched.checkpoint is None


@mock_aws
def test_get_connector_not_found(dynamodb_table, dao, tenant_context):
    with pytest.raises(DaoResourceNotFoundError):
        dao.get_connector(
            GetConnectorRequest(
                tenant_context=tenant_context,
                connector_id="no-such-id",
            )
        )


@mock_aws
def test_list_connectors_pagination(dynamodb_table, dao, tenant_context):
    ids = []
    for i in range(3):
        container_props = ContainerProperties(
            execution_role_arn="arn:role",
            image_uri="uri",
            job_role_arn="arn:job",
            environment=[],
            resource_requirements=ResourceRequirements(cpu=512 + i * 128, memory=1024 + i * 256),
            timeout=0,
        )

        resp = dao.create_connector(
            CreateConnectorRequest(
                tenant_context=tenant_context,
                name=f"conn-{i}",
                description=None,
                container_properties=container_props,
            )
        )
        ids.append(resp.connector_id)

    list_req = ListConnectorsRequest(
        tenant_context=tenant_context,
        max_results=2,
    )
    page1: ListConnectorsResponse = dao.list_connectors(list_req)
    assert len(page1.connectors) == 2
    assert page1.next_token is not None

    list_req2 = ListConnectorsRequest(
        tenant_context=tenant_context,
        max_results=2,
        next_token=page1.next_token,
    )
    page2: ListConnectorsResponse = dao.list_connectors(list_req2)
    assert len(page2.connectors) == 1
    assert page2.next_token is None


@mock_aws
def test_delete_connector_and_conflict(dynamodb_table, dao, tenant_context):
    container_props = ContainerProperties(
        execution_role_arn="arn:role",
        image_uri="uri",
        job_role_arn="arn:job",
        environment=[],
        resource_requirements=ResourceRequirements(cpu=1024, memory=2048),
        timeout=0,
    )

    resp = dao.create_connector(
        CreateConnectorRequest(
            tenant_context=tenant_context,
            name="to-delete",
            description=None,
            container_properties=container_props,
        )
    )
    cid = resp.connector_id

    # Delete when status=AVAILABLE → success
    dao.delete_connector(
        DeleteConnectorRequest(
            tenant_context=tenant_context,
            connector_id=cid,
        )
    )
    with pytest.raises(DaoResourceNotFoundError):
        dao.get_connector(
            GetConnectorRequest(
                tenant_context=tenant_context,
                connector_id=cid,
            )
        )

    # Re-create and set to IN_USE → delete should conflict
    resp2 = dao.create_connector(
        CreateConnectorRequest(
            tenant_context=tenant_context,
            name="to-delete-2",
            description=None,
            container_properties=container_props,
        )
    )
    cid2 = resp2.connector_id

    dao.update_connector_status(
        UpdateConnectorStatusRequest(
            tenant_context=tenant_context,
            connector_id=cid2,
            status=ConnectorStatus.IN_USE,
        )
    )

    with pytest.raises(DaoConflictError):
        dao.delete_connector(
            DeleteConnectorRequest(
                tenant_context=tenant_context,
                connector_id=cid2,
            )
        )


@mock_aws
def test_update_connector_status_and_not_found(dynamodb_table, dao, tenant_context):
    container_props = ContainerProperties(
        execution_role_arn="arn:role",
        image_uri="uri",
        job_role_arn="arn:job",
        environment=[],
        resource_requirements=ResourceRequirements(cpu=2048, memory=4096),
        timeout=0,
    )

    resp = dao.create_connector(
        CreateConnectorRequest(
            tenant_context=tenant_context,
            name="update-test",
            description=None,
            container_properties=container_props,
        )
    )
    cid = resp.connector_id

    # Update to IN_USE should succeed
    dao.update_connector_status(
        UpdateConnectorStatusRequest(
            tenant_context=tenant_context,
            connector_id=cid,
            status=ConnectorStatus.IN_USE,
        )
    )
    fetched = dao.get_connector(
        GetConnectorRequest(
            tenant_context=tenant_context,
            connector_id=cid,
        )
    )
    assert fetched.status == ConnectorStatus.IN_USE

    # Updating a non‐existent connector should raise NotFound
    with pytest.raises(DaoResourceNotFoundError):
        dao.update_connector_status(
            UpdateConnectorStatusRequest(
                tenant_context=tenant_context,
                connector_id="absent",
                status=ConnectorStatus.AVAILABLE,
            )
        )


@mock_aws
def test_put_get_delete_checkpoint(dynamodb_table, dao, tenant_context):
    container_props = ContainerProperties(
        execution_role_arn="arn:role",
        image_uri="uri",
        job_role_arn="arn:job",
        environment=[],
        resource_requirements=ResourceRequirements(cpu=1024, memory=2048),
        timeout=0,
    )

    resp = dao.create_connector(
        CreateConnectorRequest(
            tenant_context=tenant_context,
            name="cp-test",
            description=None,
            container_properties=container_props,
        )
    )
    cid = resp.connector_id

    # Put a checkpoint (no longer requires IN_USE status)
    dao.put_checkpoint(
        PutCheckpointRequest(
            tenant_context=tenant_context,
            connector_id=cid,
            checkpoint_data="{}",
        )
    )

    # Move to IN_USE and re‐attempt
    dao.update_connector_status(
        UpdateConnectorStatusRequest(
            tenant_context=tenant_context,
            connector_id=cid,
            status=ConnectorStatus.IN_USE,
        )
    )
    dao.put_checkpoint(
        PutCheckpointRequest(
            tenant_context=tenant_context,
            connector_id=cid,
            checkpoint_data="{}",
        )
    )

    cp_resp: GetCheckpointResponse = dao.get_checkpoint(
        GetCheckpointRequest(
            tenant_context=tenant_context,
            connector_id=cid,
        )
    )
    # Access the Checkpoint model fields directly:
    assert cp_resp.checkpoint.checkpoint_data == "{}"
    assert cp_resp.checkpoint.created_at is not None
    assert cp_resp.checkpoint.updated_at is not None

    # Delete then confirm it’s gone
    dao.delete_checkpoint(
        DeleteCheckpointRequest(
            tenant_context=tenant_context,
            connector_id=cid,
        )
    )
    with pytest.raises(DaoResourceNotFoundError):
        dao.get_checkpoint(
            GetCheckpointRequest(
                tenant_context=tenant_context,
                connector_id=cid,
            )
        )

    # Deleting again should also raise NotFound
    with pytest.raises(DaoResourceNotFoundError):
        dao.delete_checkpoint(
            DeleteCheckpointRequest(
                tenant_context=tenant_context,
                connector_id=cid,
            )
        )


@mock_aws
def test_checkpoint_on_missing_connector(dao, tenant_context):
    # put_checkpoint / get_checkpoint / delete_checkpoint on a connector that doesn't exist
    with pytest.raises(DaoResourceNotFoundError):
        dao.put_checkpoint(
            PutCheckpointRequest(
                tenant_context=tenant_context,
                connector_id="nope",
                checkpoint_data="{}",
            )
        )
    with pytest.raises(DaoResourceNotFoundError):
        dao.get_checkpoint(
            GetCheckpointRequest(
                tenant_context=tenant_context,
                connector_id="nope",
            )
        )
    with pytest.raises(DaoResourceNotFoundError):
        dao.delete_checkpoint(
            DeleteCheckpointRequest(
                tenant_context=tenant_context,
                connector_id="nope",
            )
        )
