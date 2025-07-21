from datetime import UTC, datetime, timedelta

import boto3
import pytest
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID as ACCOUNT_ID

# Imports from the CustomConnectorJobs DAO under test
from common.storage.ddb.custom_connector_jobs_dao import (
    CustomConnectorJobsDao, DaoConflictError, DaoResourceNotFoundError,
    JobStatus, ListJobsRequest, StartJobRequest, UpdateJobStatusRequest)
# Imports from the CustomConnectors DAO (needed for connector‐side setup/verification)
from common.storage.ddb.custom_connectors_dao import \
    ConnectorStatus as DaoConnectorStatus
from common.storage.ddb.custom_connectors_dao import (
    ContainerProperties, CreateConnectorRequest, CustomConnectorsDao,
    GetConnectorRequest, UpdateConnectorStatusRequest)
from common.tenant import TenantContext

# Table names used in testing
CONNECTORS_TABLE = "CustomConnectors"
JOBS_TABLE = "CustomConnectorJobs"


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
def jobs_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=JOBS_TABLE,
            KeySchema=[
                {"AttributeName": "custom_connector_arn_prefix", "KeyType": "HASH"},
                {"AttributeName": "job_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "custom_connector_arn_prefix", "AttributeType": "S"},
                {"AttributeName": "job_id", "AttributeType": "S"},
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
        yield resource.Table(JOBS_TABLE)


@pytest.fixture
def jobs_dao(connectors_dao, jobs_table):
    return CustomConnectorJobsDao(jobs_table, connectors_dao)


@pytest.fixture
def tenant_context():
    return TenantContext(account_id=ACCOUNT_ID, region="us-east-1")


def create_sample_connector(
    connectors_dao: CustomConnectorsDao, tenant_context: TenantContext, *, available: bool
) -> str:
    """
    Helper: create a new connector via CustomConnectorsDao.
    If available=False, immediately mark it IN_USE.
    Returns the new connector_id.
    """
    req = CreateConnectorRequest(
        tenant_context=tenant_context,
        name="test-connector",
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
    if not available:
        connectors_dao.update_connector_status(
            UpdateConnectorStatusRequest(
                tenant_context=tenant_context, connector_id=cid, status=DaoConnectorStatus.IN_USE
            )
        )
    return cid


@mock_aws
def test_start_job_connector_not_found(jobs_dao, tenant_context):
    """If the connector doesn't exist, start_job should raise DaoResourceNotFoundError."""
    bogus_request = StartJobRequest(
        tenant_context=tenant_context, connector_id="no-such-connector", environment=[{"foo": "bar"}]
    )
    with pytest.raises(DaoResourceNotFoundError):
        jobs_dao.start_job(bogus_request)


@mock_aws
def test_start_job_conflict_when_not_available(connectors_dao, jobs_dao, tenant_context):
    """If the connector exists but is not AVAILABLE (i.e., IN_USE), start_job should raise DaoConflictError."""
    cid = create_sample_connector(connectors_dao, tenant_context, available=False)
    with pytest.raises(DaoConflictError):
        jobs_dao.start_job(
            StartJobRequest(tenant_context=tenant_context, connector_id=cid, environment=[{"foo": "bar"}])
        )


@mock_aws
def test_start_job_success(connectors_dao, jobs_dao, tenant_context):
    """A fresh AVAILABLE connector should transition to IN_USE and create a new STARTED job."""
    cid = create_sample_connector(connectors_dao, tenant_context, available=True)
    resp = jobs_dao.start_job(
        StartJobRequest(tenant_context=tenant_context, connector_id=cid, environment=[{"env": "val"}])
    )

    # The returned job_id must have the expected prefix
    assert resp.job_id.startswith("ccj-")
    assert resp.connector_id == cid
    assert resp.status == JobStatus.STARTED

    # After start_job, the connector itself must be marked IN_USE
    fetched_connector = connectors_dao.get_connector(
        GetConnectorRequest(tenant_context=tenant_context, connector_id=cid)
    )
    assert fetched_connector.status == DaoConnectorStatus.IN_USE

    # The job item must exist in DynamoDB with status=STARTED
    raw_job_item = jobs_dao.table.get_item(
        Key={"custom_connector_arn_prefix": tenant_context.get_arn_prefix(), "job_id": resp.job_id}
    ).get("Item")
    assert raw_job_item["connector_id"] == cid
    assert raw_job_item["status"] == JobStatus.STARTED.value
    assert raw_job_item["environment"] == [{"env": "val"}]


@mock_aws
def test_update_job_status_connector_not_found(jobs_dao, tenant_context):
    """If connector is missing entirely, update_job_status should raise DaoResourceNotFoundError."""
    bogus_req = UpdateJobStatusRequest(
        tenant_context=tenant_context, connector_id="no-such-conn", job_id="any-id", status=JobStatus.RUNNING
    )
    with pytest.raises(DaoResourceNotFoundError):
        jobs_dao.update_job_status(bogus_req)


@mock_aws
def test_update_job_status_job_not_found(connectors_dao, jobs_dao, tenant_context):
    """If connector exists but the job_id is not found, update_job_status should raise DaoResourceNotFoundError."""
    cid = create_sample_connector(connectors_dao, tenant_context, available=True)
    with pytest.raises(DaoResourceNotFoundError):
        jobs_dao.update_job_status(
            UpdateJobStatusRequest(
                tenant_context=tenant_context,
                connector_id=cid,
                job_id="nonexistent-job",
                status=JobStatus.RUNNING,
            )
        )


@mock_aws
def test_update_job_status_conflict_on_terminal(connectors_dao, jobs_dao, tenant_context):
    """
    If a job is already in terminal status (STOPPED or FAILED),
    subsequent update_job_status calls should raise DaoConflictError.
    """
    cid = create_sample_connector(connectors_dao, tenant_context, available=True)
    start_resp = jobs_dao.start_job(
        StartJobRequest(tenant_context=tenant_context, connector_id=cid, environment=[{"foo": "bar"}])
    )

    # First, move it to STOPPED
    jobs_dao.update_job_status(
        UpdateJobStatusRequest(
            tenant_context=tenant_context, connector_id=cid, job_id=start_resp.job_id, status=JobStatus.STOPPED
        )
    )

    # Now attempting to change it again should conflict
    with pytest.raises(DaoConflictError):
        jobs_dao.update_job_status(
            UpdateJobStatusRequest(
                tenant_context=tenant_context, connector_id=cid, job_id=start_resp.job_id, status=JobStatus.RUNNING
            )
        )


@mock_aws
def test_update_job_status_non_terminal_and_terminal(connectors_dao, jobs_dao, tenant_context):
    """
    1. Start a job (connector → IN_USE).
    2. Update it to RUNNING → connector stays IN_USE, no TTL on job yet.
    3. Update it to STOPPED → connector flips back to AVAILABLE, TTL is set.
    """
    cid = create_sample_connector(connectors_dao, tenant_context, available=True)
    start_resp = jobs_dao.start_job(
        StartJobRequest(tenant_context=tenant_context, connector_id=cid, environment=[{"x": "y"}])
    )

    # Step 2: Move to RUNNING
    req_running = UpdateJobStatusRequest(
        tenant_context=tenant_context,
        connector_id=cid,
        job_id=start_resp.job_id,
        status=JobStatus.RUNNING,
        batch_job_id="batch-123",
    )
    jobs_dao.update_job_status(req_running)

    # The connector should still be IN_USE
    fetched_after_running = connectors_dao.get_connector(
        GetConnectorRequest(tenant_context=tenant_context, connector_id=cid)
    )
    assert fetched_after_running.status == DaoConnectorStatus.IN_USE

    # The job record should now have status=RUNNING and batch_job_id set, but no TTL
    raw1 = jobs_dao.table.get_item(
        Key={"custom_connector_arn_prefix": tenant_context.get_arn_prefix(), "job_id": start_resp.job_id}
    ).get("Item")
    assert raw1["status"] == JobStatus.RUNNING.value
    assert raw1["batch_job_id"] == "batch-123"
    assert "ttl" not in raw1

    # Step 3: Move to STOPPED
    before_stop = datetime.now(UTC)
    req_stopped = UpdateJobStatusRequest(
        tenant_context=tenant_context, connector_id=cid, job_id=start_resp.job_id, status=JobStatus.STOPPED
    )
    jobs_dao.update_job_status(req_stopped)

    # Now the connector should be AVAILABLE again
    fetched_after_stopped = connectors_dao.get_connector(
        GetConnectorRequest(tenant_context=tenant_context, connector_id=cid)
    )
    assert fetched_after_stopped.status == DaoConnectorStatus.AVAILABLE

    # The job record should now include a TTL approximately 7 days out
    raw2 = jobs_dao.table.get_item(
        Key={"custom_connector_arn_prefix": tenant_context.get_arn_prefix(), "job_id": start_resp.job_id}
    ).get("Item")
    assert raw2["status"] == JobStatus.STOPPED.value
    assert "ttl" in raw2

    # Verify TTL is at least (before_stop + 7 days)
    expires_at_ts = int(raw2["ttl"])  # Convert from string to int
    expected_min = int((before_stop + timedelta(days=7)).timestamp())
    assert expires_at_ts >= expected_min


@mock_aws
def test_list_jobs_connector_not_found(jobs_dao, tenant_context):
    """Listing jobs for a non‐existent connector should raise DaoResourceNotFoundError."""
    bogus_req = ListJobsRequest(tenant_context=tenant_context, connector_id="no-connector")
    with pytest.raises(DaoResourceNotFoundError):
        jobs_dao.list_jobs(bogus_req)


@mock_aws
def test_list_jobs_basic_and_pagination(connectors_dao, jobs_dao, tenant_context):
    """
    1. Start 5 jobs under one connector → verifies pagination and filtering.
    2. Start 2 jobs under a second connector → ensure they don't appear when listing first connector.
    3. Test `status` filter only returns matching items.
    """
    # Create two connectors
    cid1 = create_sample_connector(connectors_dao, tenant_context, available=True)
    cid2 = create_sample_connector(connectors_dao, tenant_context, available=True)

    # Start 5 jobs under cid1
    job_ids_c1 = []
    for i in range(5):
        resp = jobs_dao.start_job(
            StartJobRequest(tenant_context=tenant_context, connector_id=cid1, environment=[{"i": i}])
        )
        job_ids_c1.append(resp.job_id)

        # After starting each, immediately move to STOPPED so that connector becomes AVAILABLE again
        jobs_dao.update_job_status(
            UpdateJobStatusRequest(
                tenant_context=tenant_context, connector_id=cid1, job_id=resp.job_id, status=JobStatus.STOPPED
            )
        )

    # Pagination: first page (max_results=3)
    first_page = jobs_dao.list_jobs(ListJobsRequest(tenant_context=tenant_context, connector_id=cid1, max_results=3))
    assert len(first_page.jobs) == 3
    assert first_page.next_token is not None

    # Second page should return the remaining 2 jobs
    second_page = jobs_dao.list_jobs(
        ListJobsRequest(
            tenant_context=tenant_context,
            connector_id=cid1,
            max_results=3,
            next_token=first_page.next_token,
        )
    )
    assert len(second_page.jobs) == 2
    assert second_page.next_token is None

    # Filtering by STOPPED should return exactly those 5 jobs
    statuses = {
        job.status
        for job in jobs_dao.list_jobs(
            ListJobsRequest(tenant_context=tenant_context, connector_id=cid1, status=JobStatus.STOPPED)
        ).jobs
    }
    assert statuses == {JobStatus.STOPPED}

    # Start 2 jobs under cid2, then move them to STOPPED as well
    job_ids_c2 = []
    for i in range(2):
        resp2 = jobs_dao.start_job(
            StartJobRequest(tenant_context=tenant_context, connector_id=cid2, environment=[{"i": i}])
        )
        job_ids_c2.append(resp2.job_id)
        jobs_dao.update_job_status(
            UpdateJobStatusRequest(
                tenant_context=tenant_context, connector_id=cid2, job_id=resp2.job_id, status=JobStatus.STOPPED
            )
        )

    # Listing jobs for cid1 must not include any jobs from cid2
    listed_c1_ids = {
        job.job_id for job in jobs_dao.list_jobs(ListJobsRequest(tenant_context=tenant_context, connector_id=cid1)).jobs
    }
    assert set(job_ids_c1) == listed_c1_ids
