"""CloudFormation custom resource handler for Custom Connector Framework lifecycle management."""

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SUCCESS = "SUCCESS"
FAILED = "FAILED"


def _raise_unsupported_request_type(request_type: str) -> None:
    """
    Raise ValueError for unsupported CloudFormation request types.

    Args:
        request_type: The unsupported request type

    Raises:
        ValueError: Always raised with descriptive message

    """
    raise ValueError(f"Unsupported request type: {request_type}")


def handler(  # pylint: disable=too-many-branches,too-many-statements  # noqa: PLR0912, PLR0915
    event: dict[str, Any], _context: Any
) -> dict:
    """
    CloudFormation custom resource handler for CCF connector lifecycle management.

    Handles Create, Update, and Delete operations for Custom Connector Framework connectors
    as part of CloudFormation stack operations. This handler translates CloudFormation
    resource properties to CCF API calls.

    Args:
        event (Dict[str, Any]): CloudFormation custom resource event
        context (Any): Lambda execution context

    Returns:
        Dict: Response containing status and resource data for CloudFormation

    """
    logger.info("Received event: %s", event)
    physical_id = event.get("PhysicalResourceId", "")
    response_data = {}
    status = SUCCESS

    try:
        properties = event["ResourceProperties"]
        client = boto3.client("ccf", endpoint_url=os.environ["CCF_ENDPOINT"])

        if event["RequestType"] == "Create":
            # Prepare container properties
            container_props = {
                "image_uri": properties["DockerImageUri"],
                "execution_role_arn": properties["ExecutionRoleArn"],
                "job_role_arn": properties["JobRoleArn"],
            }

            # Add optional resource requirements
            if "Memory" in properties or "Cpu" in properties:
                resource_reqs = {}
                if "Memory" in properties:
                    resource_reqs["memory"] = int(properties["Memory"])
                if "Cpu" in properties:
                    resource_reqs["cpu"] = float(properties["Cpu"])
                container_props["resource_requirements"] = resource_reqs

            if "Timeout" in properties:
                container_props["timeout"] = int(properties["Timeout"])

            # Create connector
            logger.info("Creating connector with properties: %s", json.dumps(container_props))
            response = client.create_custom_connector(
                name=properties["ConnectorName"],
                container_properties=container_props,
                description=properties.get("Description", ""),
            )

            logger.info("CreateCustomConnector response: %s", json.dumps(response))

            connector = response["connector"]
            physical_id = connector["connector_id"]
            response_data = {"ConnectorId": physical_id, "ConnectorArn": connector["arn"]}
            logger.info("Created connector with ID: %s", physical_id)

        elif event["RequestType"] == "Delete":
            try:
                client.delete_custom_connector(connector_id=physical_id)
                logger.info("Deleted connector: %s", physical_id)
            except ClientError:
                logger.warning("Connector %s not found - skipping delete", physical_id)

        elif event["RequestType"] == "Update":
            # Prepare container properties for the update operation
            container_props = {
                "image_uri": properties["DockerImageUri"],
                "execution_role_arn": properties["ExecutionRoleArn"],
                "job_role_arn": properties["JobRoleArn"],
            }

            # Add optional resource requirements if specified
            if "Memory" in properties or "Cpu" in properties:
                resource_reqs = {}
                if "Memory" in properties:
                    resource_reqs["memory"] = int(properties["Memory"])
                if "Cpu" in properties:
                    resource_reqs["cpu"] = float(properties["Cpu"])
                container_props["resource_requirements"] = resource_reqs

            if "Timeout" in properties:
                container_props["timeout"] = int(properties["Timeout"])

            # Call the UpdateCustomConnector API to modify the connector
            logger.info("Updating connector %s with properties: %s", physical_id, json.dumps(container_props))
            response = client.update_custom_connector(
                connector_id=physical_id,
                name=properties["ConnectorName"],
                description=properties.get("Description", ""),
                container_properties=container_props,
            )

            logger.info("UpdateCustomConnector response: %s", json.dumps(response))
            connector = response["connector"]
            response_data = {"ConnectorId": connector["connector_id"], "ConnectorArn": connector["arn"]}
            logger.info("Updated connector data: %s", json.dumps(response_data))

        else:
            _raise_unsupported_request_type(event["RequestType"])

        logger.info("Sending SUCCESS response with data: %s", json.dumps(response_data))

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Operation failed: %s", exc, exc_info=True)
        status = FAILED
        response_data = {"Error": str(exc)}
        logger.info("Sending FAILED response with data: %s", json.dumps(response_data))

    # Return the response data for CloudFormation
    return {"Data": response_data, "Status": status, "PhysicalResourceId": physical_id}
