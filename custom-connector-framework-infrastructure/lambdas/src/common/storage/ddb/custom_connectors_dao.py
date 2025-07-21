"""DAO for interacting with the CustomConnectors DynamoDB table."""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Union

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from mypy_boto3_dynamodb.service_resource import Table
from pydantic import BaseModel, Field, field_validator

from common.tenant import TenantContext


class ConnectorStatus(str, Enum):
    """Enum representing the status of a connector."""

    AVAILABLE = "AVAILABLE"
    IN_USE = "IN_USE"


class ResourceRequirements(BaseModel):
    """Model for resource requirements of a connector."""

    cpu: Union[float, Decimal]  # e.g. 1.5 for 1.5 vCPU
    memory: int  # in MiB

    @field_validator("cpu")
    @classmethod
    def convert_cpu_to_decimal(cls, v):
        """Convert CPU float to Decimal for DynamoDB compatibility."""
        if isinstance(v, float):
            return Decimal(str(v))
        return v


class UpdateResourceRequirements(BaseModel):
    """Model for resource requirements of a connector in update operations."""

    cpu: Union[float, Decimal, None] = Field(default=None)
    memory: int | None = Field(default=None)

    @field_validator("cpu")
    @classmethod
    def convert_cpu_to_decimal(cls, v):
        """Convert CPU float to Decimal for DynamoDB compatibility."""
        if isinstance(v, float):
            return Decimal(str(v))

        if isinstance(v, Decimal):
            return float(v)
        return v


class ContainerProperties(BaseModel):
    """Model for container properties of a connector."""

    execution_role_arn: str
    image_uri: str
    job_role_arn: str
    resource_requirements: ResourceRequirements
    timeout: int = Field(default=3600, ge=0)


class UpdateContainerProperties(BaseModel):
    """Model for container properties of a connector in update operations."""

    execution_role_arn: str | None = Field(default=None)
    image_uri: str | None = Field(default=None)
    job_role_arn: str | None = Field(default=None)
    resource_requirements: UpdateResourceRequirements | None = Field(default=None)
    timeout: int | None = Field(default=None, ge=0)


class CreateConnectorRequest(BaseModel):
    """Request model for creating a connector."""

    tenant_context: TenantContext
    name: str
    description: str | None
    container_properties: ContainerProperties


class CreateConnectorResponse(BaseModel):
    """Response model for creating a connector."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: ConnectorStatus
    version: int


class UpdateConnectorRequest(BaseModel):
    """Request model for updating a connector."""

    tenant_context: TenantContext
    connector_id: str
    name: str | None = None
    description: str | None = None
    container_properties: UpdateContainerProperties | None = None


class UpdateConnectorResponse(BaseModel):
    """Response model for updating a connector."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    description: str | None
    status: ConnectorStatus
    version: int


class GetConnectorRequest(BaseModel):
    """Request model for getting a connector."""

    tenant_context: TenantContext
    connector_id: str


class GetConnectorResponse(BaseModel):
    """Response model for getting a connector."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    container_properties: ContainerProperties
    description: str | None
    status: ConnectorStatus
    checkpoint: dict | None
    version: int


class ListConnectorsRequest(BaseModel):
    """Request model for listing connectors."""

    tenant_context: TenantContext
    max_results: int = 50
    next_token: str | None = None


class ConnectorSummary(BaseModel):
    """Summary model for a connector."""

    connector_id: str
    arn: str
    name: str
    created_at: datetime
    updated_at: datetime
    description: str | None
    status: ConnectorStatus
    version: int


class ListConnectorsResponse(BaseModel):
    """Response model for listing connectors."""

    connectors: list[ConnectorSummary]
    next_token: str | None = None


class DeleteConnectorRequest(BaseModel):
    """Request model for deleting a connector."""

    tenant_context: TenantContext
    connector_id: str


class UpdateConnectorStatusRequest(BaseModel):
    """Request model for updating a connector status."""

    tenant_context: TenantContext
    connector_id: str
    status: ConnectorStatus


class PutCheckpointRequest(BaseModel):
    """Request model for putting a checkpoint."""

    tenant_context: TenantContext
    connector_id: str
    checkpoint_data: str


class GetCheckpointRequest(BaseModel):
    """Request model for getting a checkpoint."""

    tenant_context: TenantContext
    connector_id: str


class DeleteCheckpointRequest(BaseModel):
    """Request model for deleting a checkpoint."""

    tenant_context: TenantContext
    connector_id: str


class Checkpoint(BaseModel):
    """Model for a checkpoint."""

    checkpoint_data: str
    created_at: str
    updated_at: str


class GetCheckpointResponse(BaseModel):
    """Response model for getting a checkpoint."""

    checkpoint: Checkpoint


class DaoConflictError(Exception):
    """Exception raised when there is a conflict with a resource."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DaoResourceNotFoundError(Exception):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DaoInternalError(Exception):
    """Exception raised for internal DAO errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CustomConnectorsDao:
    """DAO for interacting with the CustomConnectors DynamoDB table."""

    def __init__(self, table: Table):
        self.table = table

    def _get_arn_prefix(self, tenant_context: TenantContext) -> str:
        return tenant_context.get_arn_prefix()

    def _raise_connector_not_found(self, connector_id: str) -> None:
        """Raise connector not found error."""
        raise DaoResourceNotFoundError(f"Connector {connector_id} not found")

    def create_connector(self, request: CreateConnectorRequest) -> CreateConnectorResponse:
        """Create a new connector."""
        now_iso = datetime.now(UTC).isoformat()
        connector_id = f"cc-{uuid.uuid4().hex[:12]}"
        arn = request.tenant_context.get_connector_arn(connector_id)

        item = {
            "custom_connector_arn_prefix": self._get_arn_prefix(request.tenant_context),
            "connector_id": connector_id,
            "arn": arn,
            "name": request.name,
            "description": request.description,
            "container_properties": request.container_properties.model_dump(),
            "status": ConnectorStatus.AVAILABLE.value,
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,  # Initialize version to 1
        }

        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(connector_id)",
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                raise DaoConflictError(f"Connector with ID {connector_id} already exists") from error
            raise DaoInternalError(f"Failed to create connector: {error.response['Error']['Message']}") from error

        return CreateConnectorResponse(
            connector_id=connector_id,
            arn=arn,
            name=request.name,
            created_at=datetime.fromisoformat(now_iso),
            updated_at=datetime.fromisoformat(now_iso),
            status=ConnectorStatus.AVAILABLE,
            version=1,  # Return version 1
        )

    def get_connector(self, request: GetConnectorRequest) -> GetConnectorResponse:
        """Get a connector by ID."""
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        try:
            response = self.table.get_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "connector_id": request.connector_id,
                }
            )
        except ClientError as error:
            raise DaoInternalError(f"Failed to retrieve connector: {error.response['Error']['Message']}") from error

        item = response.get("Item")
        if not item:
            raise DaoResourceNotFoundError(f"Connector {request.connector_id} not found")

        return GetConnectorResponse(
            connector_id=item["connector_id"],
            arn=item["arn"],
            name=item["name"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]),
            status=ConnectorStatus(item["status"]),
            container_properties=ContainerProperties.model_validate(item["container_properties"]),
            description=item.get("description"),
            checkpoint=item.get("checkpoint"),
            version=item.get("version", 1),
        )

    def list_connectors(self, request: ListConnectorsRequest) -> ListConnectorsResponse:
        """List connectors."""
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        query_kwargs = {
            "KeyConditionExpression": Key("custom_connector_arn_prefix").eq(arn_prefix),
            "Limit": request.max_results,
        }
        if request.next_token:
            query_kwargs["ExclusiveStartKey"] = json.loads(request.next_token)

        try:
            response = self.table.query(**query_kwargs)
        except ClientError as error:
            raise DaoInternalError(f"Failed to list connectors: {error.response['Error']['Message']}") from error

        summaries = [
            ConnectorSummary(
                connector_id=item["connector_id"],
                arn=item["arn"],
                name=item["name"],
                created_at=datetime.fromisoformat(item["created_at"]),
                updated_at=datetime.fromisoformat(item["updated_at"]),
                description=item.get("description"),
                status=ConnectorStatus(item["status"]),
                version=item.get("version", 1),
            )
            for item in response.get("Items", [])
        ]
        next_token = response.get("LastEvaluatedKey")
        return ListConnectorsResponse(
            connectors=summaries,
            next_token=json.dumps(next_token) if next_token else None,
        )

    def delete_connector(self, request: DeleteConnectorRequest) -> None:
        """Delete a connector by ID."""
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        try:
            self.table.delete_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "connector_id": request.connector_id,
                },
                ConditionExpression="attribute_exists(connector_id) AND #st <> :inuse",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":inuse": ConnectorStatus.IN_USE.value},
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                # Either it didn't exist, or it existed with status=IN_USE
                try:
                    get_req = GetConnectorRequest(
                        tenant_context=request.tenant_context,
                        connector_id=request.connector_id,
                    )
                    self.get_connector(get_req)
                    # If get succeeded, the delete failed because status == IN_USE
                    raise DaoConflictError(f"Connector '{request.connector_id}' is currently IN_USE") from error
                except DaoResourceNotFoundError:
                    raise DaoResourceNotFoundError(f"Connector '{request.connector_id}' not found") from error
            raise DaoInternalError(f"Failed to delete connector: {error.response['Error']['Message']}") from error

    def update_connector_status(self, request: UpdateConnectorStatusRequest) -> None:
        """Update the status of a connector."""
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        now_iso = datetime.now(UTC).isoformat()

        try:
            # First get the current item to get the version
            response = self.table.get_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "connector_id": request.connector_id,
                }
            )

            item = response.get("Item")
            if not item:
                raise DaoResourceNotFoundError("Connector 'request.connector_id' not found") from None

            # Get the current version for optimistic locking
            current_version = item.get("version", 1)
            new_version = current_version + 1

            # Update the status, version, and updated_at timestamp
            self.table.update_item(
                Key={"custom_connector_arn_prefix": arn_prefix, "connector_id": request.connector_id},
                UpdateExpression="SET #st = :status, version = :new_version, updated_at = :updated_at",
                ConditionExpression="version = :current_version",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":status": request.status.value,
                    ":current_version": current_version,
                    ":new_version": new_version,
                    ":updated_at": now_iso,
                },
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                raise DaoConflictError(f"Connector '{request.connector_id}' was modified by another process") from error
            raise DaoInternalError(
                f"Failed to update connector status: {error.response['Error']['Message']}"
            ) from error

    def put_checkpoint(self, request: PutCheckpointRequest) -> None:
        """Put a checkpoint for a connector."""
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        now_iso = datetime.now(UTC).isoformat()
        checkpoint_obj = {
            "checkpoint_data": request.checkpoint_data,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        try:
            # First get the current item to get the version
            response = self.table.get_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "connector_id": request.connector_id,
                }
            )

            item = response.get("Item")
            if not item:
                raise DaoResourceNotFoundError("Connector 'request.connector_id' not found") from None

            # Get the current version for optimistic locking
            current_version = item.get("version", 1)
            new_version = current_version + 1

            # Update the checkpoint and version
            self.table.update_item(
                Key={"custom_connector_arn_prefix": arn_prefix, "connector_id": request.connector_id},
                UpdateExpression="SET checkpoint = :cp, version = :new_version, updated_at = :updated_at",
                ConditionExpression="version = :current_version",
                ExpressionAttributeValues={
                    ":cp": checkpoint_obj,
                    ":current_version": current_version,
                    ":new_version": new_version,
                    ":updated_at": now_iso,
                },
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                raise DaoConflictError(f"Connector '{request.connector_id}' was modified by another process") from error
            raise DaoInternalError(f"Failed to put checkpoint: {error.response['Error']['Message']}") from error

    def get_checkpoint(self, request: GetCheckpointRequest) -> GetCheckpointResponse:
        """Get a checkpoint for a connector."""
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        try:
            response = self.table.get_item(
                Key={"custom_connector_arn_prefix": arn_prefix, "connector_id": request.connector_id},
                ProjectionExpression="checkpoint",
            )
        except ClientError as error:
            raise DaoInternalError(f"Failed to retrieve checkpoint: {error.response['Error']['Message']}") from error

        item = response.get("Item")
        if not item:
            raise DaoResourceNotFoundError(f"Connector '{request.connector_id}' not found") from None

        checkpoint = item.get("checkpoint")
        if not checkpoint:
            raise DaoResourceNotFoundError(f"Checkpoint for connector '{request.connector_id}' not found")

        return GetCheckpointResponse(
            checkpoint=Checkpoint(
                checkpoint_data=checkpoint["checkpoint_data"],
                created_at=checkpoint["created_at"],
                updated_at=checkpoint["updated_at"],
            )
        )

    def delete_checkpoint(self, request: DeleteCheckpointRequest) -> None:
        """Delete a checkpoint for a connector."""
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        now_iso = datetime.now(UTC).isoformat()

        try:
            # First get the current item to get the version and check if checkpoint exists
            response = self.table.get_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "connector_id": request.connector_id,
                }
            )

            item = response.get("Item")
            if not item:
                raise DaoResourceNotFoundError("Connector 'request.connector_id' not found") from None

            if "checkpoint" not in item:
                raise DaoResourceNotFoundError(f"No checkpoint to delete for connector '{request.connector_id}'")

            # Get the current version for optimistic locking
            current_version = item.get("version", 1)
            new_version = current_version + 1

            # Remove the checkpoint and update version
            self.table.update_item(
                Key={"custom_connector_arn_prefix": arn_prefix, "connector_id": request.connector_id},
                UpdateExpression="REMOVE checkpoint SET version = :new_version, updated_at = :updated_at",
                ConditionExpression="version = :current_version",
                ExpressionAttributeValues={
                    ":current_version": current_version,
                    ":new_version": new_version,
                    ":updated_at": now_iso,
                },
            )
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                raise DaoConflictError(f"Connector '{request.connector_id}' was modified by another process") from error
            raise DaoInternalError(f"Failed to delete checkpoint: {error.response['Error']['Message']}") from error

    def update_connector(self, request: UpdateConnectorRequest) -> UpdateConnectorResponse:
        """
        Update a custom connector with the provided information.

        This method implements version-based optimistic locking to prevent concurrent updates.
        It only modifies fields that are explicitly provided in the request and preserves
        existing values for fields not included.

        Args:
            request (UpdateConnectorRequest): Contains connector ID and fields to update

        Returns:
            UpdateConnectorResponse: Contains the updated connector information

        Raises:
            DaoResourceNotFoundError: When the specified connector does not exist
            DaoConflictError: When another process has modified the connector concurrently
            DaoInternalError: When a database operation fails

        """
        arn_prefix = self._get_arn_prefix(request.tenant_context)
        now_iso = datetime.now(UTC).isoformat()

        try:
            # Get the current item from DynamoDB
            response = self.table.get_item(
                Key={
                    "custom_connector_arn_prefix": arn_prefix,
                    "connector_id": request.connector_id,
                }
            )

            item = response.get("Item")
            if not item:
                self._raise_connector_not_found(request.connector_id)

            # Get the current version for optimistic locking
            current_version = item.get("version", 1)
            new_version = current_version + 1

            # Update the fields that were provided in the request
            if request.name is not None:
                item["name"] = request.name

            if request.description is not None:
                item["description"] = request.description

            if request.container_properties is not None:
                item["container_properties"] = request.container_properties.model_dump()

            # Always update the updated_at timestamp and version
            item["updated_at"] = now_iso
            item["version"] = new_version

            # Write the updated item back to DynamoDB with optimistic locking
            try:
                self.table.put_item(
                    Item=item,
                    ConditionExpression="version = :current_version",
                    ExpressionAttributeValues={":current_version": current_version},
                )
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    raise DaoConflictError(
                        f"Connector '{request.connector_id}' was modified by another process"
                    ) from error
                raise DaoInternalError(f"Failed to update connector: {error.response['Error']['Message']}") from error

            # Return the updated connector
            return UpdateConnectorResponse(
                connector_id=item["connector_id"],
                arn=item["arn"],
                name=item["name"],
                created_at=datetime.fromisoformat(item["created_at"]),
                updated_at=datetime.fromisoformat(item["updated_at"]),
                description=item.get("description"),
                status=ConnectorStatus(item["status"]),
                version=new_version,
            )

        except ClientError as error:
            raise DaoInternalError(f"Failed to update connector: {error.response['Error']['Message']}") from error
