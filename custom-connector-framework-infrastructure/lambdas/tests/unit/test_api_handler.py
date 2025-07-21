import json

from api_handler import handler


class DummyLambdaContext:
    def __init__(self):
        self.function_name = "testFunction"
        self.memory_limit_in_mb = 128
        self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:testFunction"
        self.aws_request_id = "test-request-id"


def make_event(
    http_method: str,
    path: str,
    path_params: dict = None,
    query_params: dict = None,
    body: dict = None,
) -> dict:
    """
    Construct a minimal API Gateway Proxy event with:
      - httpMethod
      - path
      - pathParameters
      - queryStringParameters
      - body (JSON-stringified if provided)
      - requestContext.identity.accountId (so extract_tenant_context() will see it)
    """
    return {
        "httpMethod": http_method,
        "path": path,
        "headers": {},
        "pathParameters": path_params or {},
        "queryStringParameters": query_params or {},
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
        "requestContext": {"identity": {"accountId": "123456789012"}},
    }


def test_create_custom_connector():
    event = make_event(
        http_method="POST",
        path="/api/v1/custom-connectors",
        body={
            "name": "test-conn",
            "container_properties": {
                "execution_role_arn": "arn:role",
                "image_uri": "uri",
                "job_role_arn": "arn:job",
                "environment": [],
                "resource_requirements": {"cpu": 1024, "memory": 2048},
                "timeout": 0,
            },
            "": {"application_id": "app", "data_source_id": "ds"},
        },
    )
    response: dict = handler(event, DummyLambdaContext())

    assert isinstance(response, dict)
    assert "statusCode" in response


def test_get_custom_connector():
    event = make_event(
        http_method="GET",
        path="/api/v1/custom-connectors/abc123",
        path_params={"connector_id": "abc123"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_list_custom_connectors_with_query_params():
    event = make_event(
        http_method="GET",
        path="/api/v1/custom-connectors",
        query_params={"max_results": "10", "next_token": "tok123"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_delete_custom_connector():
    event = make_event(
        http_method="DELETE",
        path="/api/v1/custom-connectors/xyz789",
        path_params={"connector_id": "xyz789"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_start_custom_connector_job():
    event = make_event(
        http_method="POST",
        path="/api/v1/custom-connectors/conn123/jobs",
        path_params={"connector_id": "conn123"},
        body={"environment": [{"key": "value"}]},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_stop_custom_connector_job():
    event = make_event(
        http_method="POST",
        path="/api/v1/custom-connectors/conn123/jobs/job456/stop",
        path_params={"connector_id": "conn123", "job_id": "job456"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_list_custom_connector_jobs_with_status_and_pagination():
    event = make_event(
        http_method="GET",
        path="/api/v1/custom-connectors/conn123/jobs",
        path_params={"connector_id": "conn123"},
        query_params={"status": "RUNNING", "max_results": "5", "next_token": "tokXYZ"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_put_custom_connector_checkpoint():
    event = make_event(
        http_method="PUT",
        path="/api/v1/custom-connectors/connABC/checkpoint",
        path_params={"connector_id": "connABC"},
        body={"checkpoint_data": '{"foo":"bar"}'},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_get_custom_connector_checkpoint():
    event = make_event(
        http_method="GET",
        path="/api/v1/custom-connectors/connABC/checkpoint",
        path_params={"connector_id": "connABC"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_delete_custom_connector_checkpoint():
    event = make_event(
        http_method="DELETE",
        path="/api/v1/custom-connectors/connABC/checkpoint",
        path_params={"connector_id": "connABC"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_batch_put_custom_connector_documents():
    event = make_event(
        http_method="POST",
        path="/api/v1/custom-connectors/conn123/documents",
        path_params={"connector_id": "conn123"},
        body={"documents": [{"document_id": "d1", "checksum": "cs1", "source": "src1"}]},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_batch_delete_custom_connector_documents():
    event = make_event(
        http_method="DELETE",
        path="/api/v1/custom-connectors/conn123/documents",
        path_params={"connector_id": "conn123"},
        body={"document_ids": ["d1", "d2"]},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_update_custom_connector():
    event = make_event(
        http_method="PUT",
        path="/api/v1/custom-connectors/abc123",
        path_params={"connector_id": "abc123"},
        body={
            "name": "updated-connector",
            "description": "Updated description",
            "container_properties": {
                "execution_role_arn": "arn:aws:iam::123456789012:role/updated-execution-role",
                "image_uri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/updated-image:latest",
                "job_role_arn": "arn:aws:iam::123456789012:role/updated-job-role",
                "resource_requirements": {"cpu": 2.0, "memory": 4096},
                "timeout": 7200,
            },
        },
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response


def test_list_custom_connector_documents_with_pagination():
    event = make_event(
        http_method="GET",
        path="/api/v1/custom-connectors/conn123/documents",
        path_params={"connector_id": "conn123"},
        query_params={"max_results": "3", "next_token": "tok123"},
    )
    response: dict = handler(event, DummyLambdaContext())
    assert isinstance(response, dict)
    assert "statusCode" in response
