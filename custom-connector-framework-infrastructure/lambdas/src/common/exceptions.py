"""Exceptions for the Custom Connector Framework."""

from enum import Enum
from http import HTTPStatus


class ErrorType(str, Enum):
    """Enum for error types."""

    BAD_REQUEST = "BadRequestException"
    CONFLICT = "ConflictException"
    INTERNAL_SERVER_ERROR = "InternalServerError"
    RESOURCE_NOT_FOUND = "ResourceNotFoundException"
    RESOURCE_LIMIT_EXCEEDED = "ResourceLimitExceededException"
    SERVICE_UNAVAILABLE = "ServiceUnavailableException"
    THROTTLING = "ThrottlingException"
    UNAUTHORIZED = "UnauthorizedException"


class CustomConnectorFrameworkError(Exception):
    """Base exception for the Custom Connector Framework."""

    def __init__(
        self,
        message: str,
        status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR,
        error_type: ErrorType = ErrorType.INTERNAL_SERVER_ERROR,
    ) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message
            status_code: The HTTP status code
            error_type: The error type

        """
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        super().__init__(self.message)


class BadRequestError(CustomConnectorFrameworkError):
    """Exception raised when a request is invalid."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.BAD_REQUEST, ErrorType.BAD_REQUEST)


class ConflictError(CustomConnectorFrameworkError):
    """Exception raised when a resource already exists."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.CONFLICT, ErrorType.CONFLICT)


class ResourceNotFoundError(CustomConnectorFrameworkError):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.NOT_FOUND, ErrorType.RESOURCE_NOT_FOUND)


class ResourceLimitExceededError(CustomConnectorFrameworkError):
    """Exception raised when a resource limit is exceeded."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.BAD_REQUEST, ErrorType.RESOURCE_LIMIT_EXCEEDED)


class ServiceUnavailableError(CustomConnectorFrameworkError):
    """Exception raised when the service is unavailable."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.SERVICE_UNAVAILABLE, ErrorType.SERVICE_UNAVAILABLE)


class ThrottlingError(CustomConnectorFrameworkError):
    """Exception raised when the request is throttled."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.TOO_MANY_REQUESTS, ErrorType.THROTTLING)


class UnauthorizedError(CustomConnectorFrameworkError):
    """Exception raised when the request is unauthorized."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.UNAUTHORIZED, ErrorType.UNAUTHORIZED)


class InternalServerError(CustomConnectorFrameworkError):
    """Exception raised when there was an internal server error."""

    def __init__(self, message: str) -> None:
        """
        Initialize the exception.

        Args:
            message: The error message

        """
        super().__init__(message, HTTPStatus.INTERNAL_SERVER_ERROR, ErrorType.INTERNAL_SERVER_ERROR)
