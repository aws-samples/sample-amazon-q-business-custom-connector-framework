"""Observability utilities for the Custom Connector Framework."""

from aws_lambda_powertools import Logger, Tracer
from pydantic import BaseModel

# Initialize logger
logger = Logger(service="CustomConnectorFramework")
tracer = Tracer(service="CustomConnectorFramework")


class LogContext(BaseModel):
    """
    Pydantic model for standardized log context with key identifiers for traceability.

    All values must be strings to ensure consistent logging format.
    """

    connector_id: str | None = None
    account_id: str | None = None
    job_id: str | None = None


def create_log_context(context: LogContext) -> dict[str, str]:
    """
    Create a standardized log context dictionary from LogContext model.

    Args:
        context: LogContext model with key identifiers

    Returns:
        Dictionary containing non-None log context values

    """
    return context.model_dump(exclude_none=True)
