"""
Integration test for Amazon Q Business Custom Connector Framework APIs.

This script tests all the CCF APIs using the boto3 client.
"""

import hashlib
import json
import logging
import os
import time
import uuid

import boto3
import pytest

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class CCFIntegrationTest:
    """Integration test for CCF APIs."""

    def __init__(self):
        """Initialize the test with boto3 clients."""
        # Initialize clients
        self.cloudformation_client = boto3.client("cloudformation")

        # Get CCF endpoint from CloudFormation stack
        self.ccf_endpoint = self._get_ccf_endpoint()
        logger.info(f"Using CCF endpoint: {self.ccf_endpoint}")

        self.ccf_client = boto3.client("ccf", endpoint_url=self.ccf_endpoint)

        # Resources to track
        self.connector_id = None

        # Use fake values for image URI and IAM roles
        self.account_id = boto3.client("sts").get_caller_identity().get("Account")
        self.region = boto3.session.Session().region_name
        self.image_uri = f"{self.account_id}.dkr.ecr.{self.region}.amazonaws.com/fake-hello-world:latest"
        self.execution_role_arn = f"arn:aws:iam::{self.account_id}:role/fake-execution-role"
        self.job_role_arn = f"arn:aws:iam::{self.account_id}:role/fake-job-role"

        self.job_id = None
        self.document_ids = []

    def _get_ccf_endpoint(self) -> str:
        """
        Get the CCF endpoint from CloudFormation stack outputs.

        Returns:
            str: The CCF API endpoint URL

        """
        try:
            # Try to get the endpoint from the CustomConnectorFrameworkStack
            response = self.cloudformation_client.describe_stacks(StackName="CustomConnectorFrameworkStack")

            for output in response["Stacks"][0]["Outputs"]:
                if output["OutputKey"] == "ApiEndpoint":
                    return output["OutputValue"]

            # If we didn't find the endpoint in the outputs, try to construct it from the API ID
            for output in response["Stacks"][0]["Outputs"]:
                if output["OutputKey"] == "ApiGatewayId":
                    api_id = output["OutputValue"]
                    region = boto3.session.Session().region_name
                    return f"https://{api_id}.execute-api.{region}.amazonaws.com/prod"

            raise ValueError("Could not find API endpoint in CloudFormation outputs")

        except Exception as e:
            logger.warning(f"Could not get CCF endpoint from CloudFormation: {e}")

            # Fall back to environment variable if available
            ccf_endpoint = os.environ.get("CCF_ENDPOINT")
            if ccf_endpoint:
                return ccf_endpoint

            raise ValueError("Could not determine CCF endpoint. Please set the CCF_ENDPOINT environment variable.")

    def cleanup(self) -> None:
        """Clean up any resources created during testing."""
        logger.info("Cleaning up test resources...")

        if self.connector_id:
            try:
                logger.info(f"Deleting connector {self.connector_id}...")
                self.ccf_client.delete_custom_connector(connector_id=self.connector_id)
            except Exception as e:
                logger.warning(f"Error deleting connector: {e}")

        logger.info("Cleanup completed")


@pytest.fixture(scope="module")
def ccf_test():
    """Fixture to set up and tear down the CCF integration test."""
    test = CCFIntegrationTest()
    yield test
    test.cleanup()


def test_01_create_connector(ccf_test):
    """Test creating a custom connector."""
    logger.info("Testing CreateCustomConnector API...")

    test_connector_name = f"test-connector-{uuid.uuid4().hex[:8]}"
    test_connector_description = "Test connector for integration tests"

    response = ccf_test.ccf_client.create_custom_connector(
        name=test_connector_name,
        description=test_connector_description,
        container_properties={
            "image_uri": ccf_test.image_uri,
            "execution_role_arn": ccf_test.execution_role_arn,
            "job_role_arn": ccf_test.job_role_arn,
            "resource_requirements": {"cpu": 1, "memory": 2048},  # Updated to minimum valid memory
            "timeout": 3600,
        },
    )

    ccf_test.connector_id = response["connector"]["connector_id"]
    logger.info(f"Created connector with ID: {ccf_test.connector_id}")

    assert ccf_test.connector_id, "Connector ID should not be empty"
    assert response["connector"]["name"] == test_connector_name, "Connector name mismatch"
    assert len(ccf_test.connector_id) == 15, "Connector ID should be 15 characters"
    assert ccf_test.connector_id.startswith("cc-"), "Connector ID should start with 'cc-'"


def test_02_list_connectors(ccf_test):
    """Test listing custom connectors."""
    logger.info("Testing ListCustomConnectors API...")

    assert ccf_test.connector_id

    response = ccf_test.ccf_client.list_custom_connectors()

    connectors = response["connectors"]
    logger.info(f"Found {len(connectors)} connectors")
    assert len(connectors) <= 50, "Should not return more than 50 connectors"

    found = False
    for connector in connectors:
        if connector["connector_id"] == ccf_test.connector_id:
            found = True
            break

    assert found, f"Test connector {ccf_test.connector_id} not found in list"


def test_03_get_connector(ccf_test):
    """Test getting a custom connector."""
    logger.info("Testing GetCustomConnector API...")

    assert ccf_test.connector_id

    response = ccf_test.ccf_client.get_custom_connector(connector_id=ccf_test.connector_id)

    connector = response["connector"]
    logger.info(f"Retrieved connector: {connector['name']}")

    assert connector["connector_id"] == ccf_test.connector_id, "Connector ID mismatch"
    assert "container_properties" in connector, "Container properties should be included in response"


def test_04_update_connector(ccf_test):
    """Test updating a custom connector."""
    logger.info("Testing UpdateCustomConnector API...")

    response = ccf_test.ccf_client.get_custom_connector(connector_id=ccf_test.connector_id)
    connector = response["connector"]

    updated_description = f"{connector['description']} - Updated"

    response = ccf_test.ccf_client.update_custom_connector(
        connector_id=ccf_test.connector_id, name=connector["name"], description=updated_description
    )

    connector = response["connector"]
    logger.info(f"Updated connector: {connector['name']}")

    assert connector["description"] == updated_description, "Connector description not updated"


def test_05_put_checkpoint(ccf_test):
    """Test putting a checkpoint."""
    logger.info("Testing PutCustomConnectorCheckpoint API...")

    # Create a JSON string for checkpoint data
    checkpoint_data = json.dumps({"last_sync_time": "2024-01-01T00:00:00Z"})

    result = ccf_test.ccf_client.put_custom_connector_checkpoint(
        connector_id=ccf_test.connector_id, checkpoint_data=checkpoint_data
    )
    logger.info("Checkpoint created successfully")

    assert result


def test_06_get_checkpoint(ccf_test):
    """Test getting a checkpoint."""
    logger.info("Testing GetCustomConnectorCheckpoint API...")

    response = ccf_test.ccf_client.get_custom_connector_checkpoint(connector_id=ccf_test.connector_id)

    checkpoint = response["checkpoint"]
    logger.info(f"Retrieved checkpoint: {checkpoint}")

    assert isinstance(checkpoint["checkpoint_data"], str), "Checkpoint data should be a string"


def test_07_start_job(ccf_test):
    """Test starting a custom connector job."""
    logger.info("Testing StartCustomConnectorJob API...")

    response = ccf_test.ccf_client.start_custom_connector_job(
        connector_id=ccf_test.connector_id, environment=[{"name": "TEST_VAR", "value": "test_value"}]
    )

    ccf_test.job_id = response["job"]["job_id"]
    logger.info(f"Started job with ID: {ccf_test.job_id}")

    assert ccf_test.job_id, "Job ID should not be empty"
    assert len(ccf_test.job_id) == 16, "Job ID should be 16 characters"
    assert ccf_test.job_id.startswith("ccj-"), "Job ID should start with 'ccj-'"
    logger.info("Job will likely fail due to fake values, but API test is successful")


def test_08_list_jobs(ccf_test):
    """Test listing custom connector jobs."""
    logger.info("Testing ListCustomConnectorJobs API...")

    response = ccf_test.ccf_client.list_custom_connector_jobs(connector_id=ccf_test.connector_id)

    jobs = response["jobs"]
    logger.info(f"Found {len(jobs)} jobs")
    assert len(jobs) <= 50, "Should not return more than 50 jobs"

    if ccf_test.job_id:
        found = False
        for job in jobs:
            if job["job_id"] == ccf_test.job_id:
                found = True
                break

        assert found, f"Test job {ccf_test.job_id} not found in list"


def test_10_put_documents(ccf_test):
    """Test putting documents."""
    logger.info("Testing BatchPutCustomConnectorDocuments API...")

    assert ccf_test.connector_id

    # Create SHA-256 checksums for test data
    doc1_content = "test document 1"
    doc2_content = "test document 2"

    documents = [
        {"document_id": f"test-doc-{uuid.uuid4().hex}", "checksum": hashlib.sha256(doc1_content.encode()).hexdigest()},
        {"document_id": f"test-doc-{uuid.uuid4().hex}", "checksum": hashlib.sha256(doc2_content.encode()).hexdigest()},
    ]

    ccf_test.ccf_client.batch_put_custom_connector_documents(connector_id=ccf_test.connector_id, documents=documents)

    logger.info(f"Added {len(documents)} documents")
    ccf_test.document_ids = [doc["document_id"] for doc in documents]


def test_11_list_documents(ccf_test):
    """Test listing documents."""
    logger.info("Testing ListCustomConnectorDocuments API...")

    response = ccf_test.ccf_client.list_custom_connector_documents(connector_id=ccf_test.connector_id)

    documents = response["documents"]
    logger.info(f"Found {len(documents)} documents")
    assert len(documents) <= 50, "Should not return more than 50 documents"

    if ccf_test.document_ids:
        found_count = 0
        for doc in documents:
            if doc["document_id"] in ccf_test.document_ids:
                found_count += 1

        if found_count > 0:
            assert found_count == len(ccf_test.document_ids), "Not all test documents found in list"


def test_12_delete_documents(ccf_test):
    """Test deleting documents."""
    logger.info("Testing BatchDeleteCustomConnectorDocuments API...")

    ccf_test.ccf_client.batch_delete_custom_connector_documents(
        connector_id=ccf_test.connector_id, document_ids=ccf_test.document_ids
    )

    logger.info(f"Deleted {len(ccf_test.document_ids)} documents")

    # Verify documents were deleted
    response = ccf_test.ccf_client.list_custom_connector_documents(connector_id=ccf_test.connector_id)

    documents = response["documents"]
    for doc in documents:
        assert doc["document_id"] not in ccf_test.document_ids, f"Document {doc['document_id']} was not deleted"


def test_13_delete_checkpoint(ccf_test):
    """Test deleting a checkpoint."""
    logger.info("Testing DeleteCustomConnectorCheckpoint API...")

    ccf_test.ccf_client.delete_custom_connector_checkpoint(connector_id=ccf_test.connector_id)
    logger.info("Checkpoint deleted successfully")


def test_14_delete_connector(ccf_test):
    """Test deleting a custom connector."""
    logger.info("Testing DeleteCustomConnector API...")

    # Wait for connector to be in AVAILABLE state
    max_attempts = 10
    for i in range(max_attempts):
        response = ccf_test.ccf_client.get_custom_connector(connector_id=ccf_test.connector_id)
        status = response["connector"]["status"]
        logger.info(f"Connector status: {status}")

        if status == "AVAILABLE":
            break

        if i < max_attempts - 1:  # Don't sleep on the last attempt
            time.sleep(5)

    ccf_test.ccf_client.delete_custom_connector(connector_id=ccf_test.connector_id)
    logger.info(f"Deleted connector {ccf_test.connector_id}")
