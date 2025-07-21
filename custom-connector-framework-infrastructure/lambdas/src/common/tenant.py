"""Tenant models for the Custom Connector Framework."""

import re
from typing import Any

from pydantic import BaseModel

from common.env import AWS_REGION
from common.exceptions import BadRequestError


class TenantContext(BaseModel):
    """Model for tenant context."""

    account_id: str
    region: str

    @classmethod
    def from_arn_prefix(cls, arn_prefix: str) -> "TenantContext":
        """
        Create a TenantContext from an ARN prefix.

        Args:
            arn_prefix: ARN prefix in format 'arn:aws:ccf:region:account_id'

        Returns:
            TenantContext: The tenant context

        Raises:
            BadRequestError: If the ARN prefix format is invalid

        """
        # Parse ARN prefix using regex
        pattern = r"arn:aws:ccf:([^:]+):(\d+)"
        match = re.match(pattern, arn_prefix)

        if not match:
            raise BadRequestError("Invalid ARN prefix format")

        region, account_id = match.groups()
        return cls(account_id=account_id, region=region)

    def get_arn_prefix(self) -> str:
        """
        Get the ARN prefix for this tenant context.

        Returns:
            str: The ARN prefix

        """
        return f"arn:aws:ccf:{self.region}:{self.account_id}"

    def get_connector_arn(self, connector_id: str) -> str:
        """
        Get the ARN prefix for this tenant context.

        Returns:
            str: The ARN prefix

        """
        return f"{self.get_arn_prefix()}:custom-connector/{connector_id}"


def extract_tenant_context(event: dict[str, Any]) -> TenantContext:
    """
    Extract tenant context from the event.

    Args:
        event: The Lambda event

    Returns:
        TenantContext: The tenant context

    """
    request_context = event.get("requestContext", {})
    identity = request_context.get("identity", {})
    account_id = identity.get("accountId")

    if not account_id:
        raise BadRequestError("Account ID not found in request context")

    return TenantContext(account_id=account_id, region=AWS_REGION)
