"""Lambda function for starting Custom Connector Framework jobs on a schedule."""

import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001  # pylint: disable=unused-argument
    """
    Start CCF connector jobs on a schedule.

    Args:
        event: The Lambda event containing environment variables
        context: The Lambda context (unused)

    Returns:
        dict: Job information including job_id, status, connector_id, and created_at

    Raises:
        Exception: If the connector job fails to start

    """
    logger.info("Received event: %s", event)

    try:
        connector_id = os.environ["CUSTOM_CONNECTOR_ID"]
        environment = []

        # Convert environment variables from dict to list of name/value pairs
        if "environment" in event:
            environment = [{"name": key, "value": str(value)} for key, value in event["environment"].items()]

        client = boto3.client("ccf", endpoint_url=os.environ["CCF_ENDPOINT"])

        # Start the connector job
        response = client.start_custom_connector_job(connector_id=connector_id, environment=environment)

        return {
            "job_id": response["job"]["job_id"],
            "status": response["job"]["status"],
            "connector_id": response["job"]["connector_id"],
            "created_at": response["job"]["created_at"],
        }

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to start connector job: %s", exc)
        raise
