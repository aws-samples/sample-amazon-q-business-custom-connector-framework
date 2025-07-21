"""Response utilities for the Custom Connector Framework."""

import json
from http import HTTPStatus
from typing import Any

from aws_lambda_powertools.event_handler import Response
from pydantic import BaseModel

from common.exceptions import CustomConnectorFrameworkError

APPLICATION_JSON = "application/json"


def create_success_response(
    body: BaseModel | dict[str, Any] | list[BaseModel | dict[str, Any] | str] | str | None = None,
    status_code: int = HTTPStatus.OK,
) -> Response:
    """
    Create a success response.

    Args:
        body: The response body (can be a BaseModel, dictionary, string, or a list of BaseModel/dictionary/string)
        status_code: The HTTP status code

    Returns:
        Response: The API Gateway response

    """
    if body is None:
        return Response(
            status_code=status_code,
            content_type=APPLICATION_JSON,
        )

    if isinstance(body, list):
        # Handle list of BaseModel, Dict, or str
        processed_list = []
        for item in body:
            if isinstance(item, BaseModel):
                processed_list.append(json.loads(item.model_dump_json()))
            elif isinstance(item, dict | str):
                processed_list.append(item)
            else:
                msg = "List items must be either BaseModel, dictionary, or string"
                raise TypeError(msg)

        return Response(
            status_code=status_code,
            content_type=APPLICATION_JSON,
            body=json.dumps(processed_list),
        )

    if isinstance(body, BaseModel):
        return Response(
            status_code=status_code,
            content_type=APPLICATION_JSON,
            body=body.model_dump_json(),
        )

    if isinstance(body, dict | str):
        return Response(
            status_code=status_code,
            content_type=APPLICATION_JSON,
            body=json.dumps(body),
        )

    msg = "Body must be a BaseModel, dictionary, string, or list of BaseModel/dictionary/string"
    raise ValueError(msg)


def create_error_response(
    error: CustomConnectorFrameworkError | Exception,
    status_code: int | None = None,
) -> Response:
    """
    Create an error response.

    Args:
        error: The error
        status_code: Optional HTTP status code override

    Returns:
        Response: The API Gateway response

    """
    if isinstance(error, CustomConnectorFrameworkError):
        response_status_code = status_code if status_code is not None else error.status_code
        error_body = {
            "message": error.message,
            "errorType": error.error_type,
        }
    else:
        response_status_code = status_code if status_code is not None else HTTPStatus.INTERNAL_SERVER_ERROR
        error_body = {
            "message": str(error),
            "errorType": "InternalServerError",
        }

    return Response(
        status_code=response_status_code,
        content_type=APPLICATION_JSON,
        body=json.dumps(error_body),
    )
