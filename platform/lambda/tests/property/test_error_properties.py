"""
Property-based tests for error response format, CORS headers, error logging,
and agentId path parameter validation.

Tests exercise the ``lambda_handler`` function directly by constructing
API Gateway proxy events and asserting on the response structure.  All
external dependencies (S3 Vectors, Bedrock) are mocked at the service level.

Uses ``hypothesis`` with a minimum of 100 examples per property.
"""
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers (reused from test_crud_properties.py patterns)
# ---------------------------------------------------------------------------


def _apigw_event(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, str]] = None,
    request_id: str = "test-request-id",
) -> Dict[str, Any]:
    """Build a minimal API Gateway Lambda proxy event."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": query_params,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"requestId": request_id},
        "pathParameters": None,
        "isBase64Encoded": False,
    }


def _lambda_context() -> MagicMock:
    """Return a minimal mock Lambda context."""
    ctx = MagicMock()
    ctx.function_name = "test-handler"
    ctx.memory_limit_in_mb = 512
    ctx.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
    ctx.aws_request_id = "test-request-id"
    return ctx


# ---------------------------------------------------------------------------
# In-memory vector store mock
# ---------------------------------------------------------------------------


class _InMemoryVectorStore:
    """Minimal in-memory replacement for the S3 Vectors client."""

    def __init__(self) -> None:
        self.vectors: Dict[str, Dict[str, Any]] = {}

    def put_vectors(self, **kwargs: Any) -> Dict[str, Any]:
        for vec in kwargs.get("vectors", []):
            self.vectors[vec["key"]] = {
                "key": vec["key"],
                "data": vec.get("data", {}),
                "metadata": vec.get("metadata", {}),
            }
        return {}

    def get_vectors(self, **kwargs: Any) -> Dict[str, Any]:
        keys = kwargs.get("keys", [])
        found = [self.vectors[k] for k in keys if k in self.vectors]
        return {"vectors": found}

    def list_vectors(self, **kwargs: Any) -> Dict[str, Any]:
        return {"vectors": list(self.vectors.values())}

    def delete_vectors(self, **kwargs: Any) -> Dict[str, Any]:
        for key in kwargs.get("keys", []):
            self.vectors.pop(key, None)
        return {}

    def query_vectors(self, **kwargs: Any) -> Dict[str, Any]:
        return {"vectors": []}


def _build_patched_handler(store: _InMemoryVectorStore):
    """Import handler with mocked S3 Vectors and Bedrock clients.

    Returns the ``lambda_handler`` function with all external I/O replaced
    by the in-memory store.
    """
    mock_s3v = MagicMock()
    mock_s3v.put_vectors = store.put_vectors
    mock_s3v.get_vectors = store.get_vectors
    mock_s3v.list_vectors = store.list_vectors
    mock_s3v.delete_vectors = store.delete_vectors
    mock_s3v.query_vectors = store.query_vectors

    mock_bedrock = MagicMock()
    mock_bedrock.invoke_model.return_value = {
        "body": MagicMock(
            read=MagicMock(
                return_value=json.dumps({"embedding": [0.1] * 1024}).encode()
            )
        )
    }

    with patch("services.agent_service.boto3") as mock_boto_agent, \
         patch("services.health_service.boto3") as mock_boto_health, \
         patch("services.embedding_service.boto3") as mock_boto_embed, \
         patch("services.chat_service.AgentService") as mock_chat_as:

        mock_boto_agent.client.return_value = mock_s3v
        mock_boto_health.client.return_value = mock_s3v
        mock_boto_embed.client.return_value = mock_bedrock

        import importlib
        import services.embedding_service as embed_mod
        importlib.reload(embed_mod)
        import services.agent_service as agent_mod
        importlib.reload(agent_mod)
        import services.health_service as health_mod
        importlib.reload(health_mod)
        import services.chat_service as chat_mod
        importlib.reload(chat_mod)
        import handler as handler_mod
        importlib.reload(handler_mod)

        return handler_mod.lambda_handler


def _setup_handler():
    """Create a fresh in-memory store and return (handler, store)."""
    store = _InMemoryVectorStore()
    handler = _build_patched_handler(store)
    return handler, store


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Non-empty printable text (avoids null bytes that break JSON round-trips)
_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())

# Strategy for error-triggering scenarios via the handler
_error_scenario = st.sampled_from([
    # 400 — missing required fields on POST /agents
    {
        "method": "POST",
        "path": "/agents",
        "body": {"skills": []},
        "expected_status": 400,
        "expected_code": "VALIDATION_ERROR",
    },
    # 400 — missing agentId on POST /chat
    {
        "method": "POST",
        "path": "/chat",
        "body": {"message": "hello"},
        "expected_status": 400,
        "expected_code": "VALIDATION_ERROR",
    },
    # 400 — missing message on POST /chat
    {
        "method": "POST",
        "path": "/chat",
        "body": {"agentId": "some-id"},
        "expected_status": 400,
        "expected_code": "VALIDATION_ERROR",
    },
    # 400 — empty body on POST /agents
    {
        "method": "POST",
        "path": "/agents",
        "body": {},
        "expected_status": 400,
        "expected_code": "VALIDATION_ERROR",
    },
    # 400 — missing search params
    {
        "method": "GET",
        "path": "/agents/search",
        "body": None,
        "query_params": {},
        "expected_status": 400,
        "expected_code": "VALIDATION_ERROR",
    },
    # 404 — non-existent agent GET
    {
        "method": "GET",
        "path": "/agents/00000000-0000-0000-0000-000000000099",
        "body": None,
        "expected_status": 404,
        "expected_code": "NOT_FOUND",
    },
    # 404 — non-existent agent health check
    {
        "method": "POST",
        "path": "/agents/00000000-0000-0000-0000-000000000099/health",
        "body": None,
        "expected_status": 404,
        "expected_code": "NOT_FOUND",
    },
    # 404 — unknown route
    {
        "method": "GET",
        "path": "/nonexistent",
        "body": None,
        "expected_status": 404,
        "expected_code": "NOT_FOUND",
    },
])

# Strategy for whitespace / empty agentId strings
_whitespace_agent_id = st.one_of(
    st.just(""),
    st.text(
        alphabet=st.sampled_from([" ", "\t", "\n", "\r"]),
        min_size=1,
        max_size=20,
    ),
)

# Endpoints that accept agentId as a path parameter
_agent_id_endpoints = st.sampled_from([
    ("GET", "/agents/{agentId}"),
    ("PUT", "/agents/{agentId}"),
    ("DELETE", "/agents/{agentId}"),
    ("POST", "/agents/{agentId}/health"),
])


# ---------------------------------------------------------------------------
# Property 12: Error Response Format Invariant
# Feature: lss-workshop-platform, Property 12: Error Response Format Invariant
# ---------------------------------------------------------------------------


class TestErrorResponseFormatInvariant:
    """**Validates: Requirements 14.4, 15.1, 15.2**

    For any API error response (400, 404, 502, 500), the response body should
    be valid JSON containing error_code (string) and message (string) fields,
    and the error_code should match the expected mapping:
    400→VALIDATION_ERROR, 404→NOT_FOUND, 502→AGENT_UNREACHABLE,
    500→INTERNAL_ERROR.
    """

    @given(scenario=_error_scenario)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_error_responses_have_correct_format_and_code(
        self, scenario: Dict[str, Any]
    ) -> None:
        # Feature: lss-workshop-platform, Property 12: Error Response Format Invariant
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        event = _apigw_event(
            method=scenario["method"],
            path=scenario["path"],
            body=scenario.get("body"),
            query_params=scenario.get("query_params"),
        )
        resp = handler(event, ctx)

        # Status code matches expected
        assert resp["statusCode"] == scenario["expected_status"], (
            f"Expected {scenario['expected_status']}, got {resp['statusCode']}: "
            f"{resp['body']}"
        )

        # Body is valid JSON with required fields
        body = json.loads(resp["body"])
        assert "error_code" in body, f"Missing error_code in {body}"
        assert "message" in body, f"Missing message in {body}"
        assert isinstance(body["error_code"], str)
        assert isinstance(body["message"], str)

        # error_code matches the expected mapping
        assert body["error_code"] == scenario["expected_code"], (
            f"Expected error_code '{scenario['expected_code']}', "
            f"got '{body['error_code']}'"
        )


# ---------------------------------------------------------------------------
# Property 13: CORS Headers in Error Responses
# Feature: lss-workshop-platform, Property 13: CORS Headers in Error Responses
# ---------------------------------------------------------------------------


class TestCORSHeadersInErrorResponses:
    """**Validates: Requirements 15.3**

    For any API error response, the response headers should include
    Access-Control-Allow-Origin, Access-Control-Allow-Headers, and
    Access-Control-Allow-Methods.
    """

    @given(scenario=_error_scenario)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_error_responses_include_cors_headers(
        self, scenario: Dict[str, Any]
    ) -> None:
        # Feature: lss-workshop-platform, Property 13: CORS Headers in Error Responses
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        event = _apigw_event(
            method=scenario["method"],
            path=scenario["path"],
            body=scenario.get("body"),
            query_params=scenario.get("query_params"),
        )
        resp = handler(event, ctx)

        # Verify it's an error response
        assert resp["statusCode"] >= 400

        headers = resp.get("headers", {})
        assert "Access-Control-Allow-Origin" in headers, (
            f"Missing Access-Control-Allow-Origin in error response headers: {headers}"
        )
        assert "Access-Control-Allow-Headers" in headers, (
            f"Missing Access-Control-Allow-Headers in error response headers: {headers}"
        )
        assert "Access-Control-Allow-Methods" in headers, (
            f"Missing Access-Control-Allow-Methods in error response headers: {headers}"
        )


# ---------------------------------------------------------------------------
# Property 14: Error Logging Includes Context
# Feature: lss-workshop-platform, Property 14: Error Logging Includes Context
# ---------------------------------------------------------------------------


class TestErrorLoggingIncludesContext:
    """**Validates: Requirements 15.4**

    For any API error, the log output should contain the request_id,
    error_code, and error message at the appropriate log level.
    """

    @given(scenario=_error_scenario)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_error_log_contains_required_fields(
        self, scenario: Dict[str, Any]
    ) -> None:
        # Feature: lss-workshop-platform, Property 14: Error Logging Includes Context
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        request_id = f"req-{uuid.uuid4()}"
        event = _apigw_event(
            method=scenario["method"],
            path=scenario["path"],
            body=scenario.get("body"),
            query_params=scenario.get("query_params"),
            request_id=request_id,
        )

        # Capture log output from the handler module's logger
        import handler as handler_mod

        captured_records: List[logging.LogRecord] = []

        class _CapturingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured_records.append(record)

        capture_handler = _CapturingHandler()
        handler_mod.logger.addHandler(capture_handler)
        try:
            resp = handler(event, ctx)
        finally:
            handler_mod.logger.removeHandler(capture_handler)

        # Verify it's an error response
        assert resp["statusCode"] >= 400

        # Find ERROR-level log records that contain structured JSON
        error_logs = [
            r for r in captured_records if r.levelno >= logging.ERROR
        ]
        assert len(error_logs) > 0, (
            f"No ERROR-level log records captured for scenario: "
            f"{scenario['method']} {scenario['path']}"
        )

        # At least one error log should contain request_id, error_code, message
        found_structured = False
        for record in error_logs:
            msg = record.getMessage()
            try:
                log_data = json.loads(msg)
                if (
                    "request_id" in log_data
                    and "error_code" in log_data
                    and "message" in log_data
                ):
                    assert log_data["request_id"] == request_id
                    assert log_data["error_code"] == scenario["expected_code"]
                    assert isinstance(log_data["message"], str)
                    assert len(log_data["message"]) > 0
                    found_structured = True
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        assert found_structured, (
            f"No structured error log with request_id, error_code, and message "
            f"found. Captured log messages: "
            f"{[r.getMessage() for r in error_logs]}"
        )


# ---------------------------------------------------------------------------
# Property 20: agentId Path Parameter Validation
# Feature: lss-workshop-platform, Property 20: agentId Path Parameter Validation
# ---------------------------------------------------------------------------


class TestAgentIdPathParameterValidation:
    """**Validates: Requirements 14.5**

    For any request to an endpoint accepting agentId as a path parameter,
    if the agentId is an empty string or contains only whitespace, the API
    should return a 400 status code with a VALIDATION_ERROR.
    """

    @given(
        agent_id=_whitespace_agent_id,
        endpoint=_agent_id_endpoints,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_empty_or_whitespace_agent_id_returns_400(
        self, agent_id: str, endpoint: tuple
    ) -> None:
        # Feature: lss-workshop-platform, Property 20: agentId Path Parameter Validation
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        method, path_template = endpoint
        path = path_template.replace("{agentId}", agent_id)

        # PUT /agents/{agentId} requires a body
        body = None
        if method == "PUT":
            body = {
                "name": "test",
                "description": "test",
                "url": "http://test.example.com",
            }

        event = _apigw_event(method=method, path=path, body=body)
        resp = handler(event, ctx)

        assert resp["statusCode"] == 400, (
            f"Expected 400 for agentId={repr(agent_id)} on {method} {path}, "
            f"got {resp['statusCode']}: {resp['body']}"
        )
        resp_body = json.loads(resp["body"])
        assert resp_body["error_code"] == "VALIDATION_ERROR", (
            f"Expected VALIDATION_ERROR, got {resp_body['error_code']}"
        )
