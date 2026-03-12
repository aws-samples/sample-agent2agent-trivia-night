"""Unit tests for handler routing dispatch.

Verifies that each HTTP method/path combination is routed to the correct
service and that unknown routes return 404.  Uses the same
``_InMemoryVectorStore`` pattern from the property tests so that no real
AWS calls are made.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 3.1, 4.1
"""
import importlib
import json
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apigw_event(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, str]] = None,
    request_id: str = "test-request-id",
) -> Dict[str, Any]:
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
    ctx = MagicMock()
    ctx.function_name = "test-handler"
    ctx.memory_limit_in_mb = 512
    ctx.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
    ctx.aws_request_id = "test-request-id"
    return ctx


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


_VALID_CARD = {"name": "TestAgent", "description": "A test agent", "url": "https://example.com"}


def _build_mock_boto3(store: _InMemoryVectorStore) -> MagicMock:
    """Build a mock boto3 module whose .client() returns the right mock
    depending on the service name."""
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

    def fake_client(service_name, **kwargs):
        if service_name == "s3vectors":
            return mock_s3v
        if service_name == "bedrock-runtime":
            return mock_bedrock
        return MagicMock()

    mock_boto = MagicMock()
    mock_boto.client = fake_client
    return mock_boto


@pytest.fixture()
def handler_and_store():
    """Yield (lambda_handler, store) with all AWS I/O mocked.

    Patches ``boto3`` at the top-level *before* reloading service modules so
    that ``import boto3`` inside each module picks up the mock.
    """
    store = _InMemoryVectorStore()
    mock_boto = _build_mock_boto3(store)

    # Patch boto3 at the sys.modules level so that ``import boto3`` in any
    # reloaded module resolves to our mock.
    real_boto3 = sys.modules.get("boto3")
    sys.modules["boto3"] = mock_boto

    try:
        import services.embedding_service as embed_mod
        importlib.reload(embed_mod)
        import services.agent_service as agent_mod
        importlib.reload(agent_mod)
        import services.search_service as search_mod
        importlib.reload(search_mod)
        import services.health_service as health_mod
        importlib.reload(health_mod)
        import services.chat_service as chat_mod
        importlib.reload(chat_mod)
        import handler as handler_mod
        importlib.reload(handler_mod)

        yield handler_mod.lambda_handler, store
    finally:
        # Restore real boto3
        if real_boto3 is not None:
            sys.modules["boto3"] = real_boto3
        else:
            sys.modules.pop("boto3", None)


# ---------------------------------------------------------------------------
# POST /agents  (Requirement 1.1)
# ---------------------------------------------------------------------------

class TestPostAgents:
    def test_creates_agent_returns_201(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("POST", "/agents", body=_VALID_CARD), _lambda_context())
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert "agent_id" in body
        assert body["message"] == "Agent created successfully"

    def test_invalid_body_returns_400(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("POST", "/agents", body={"name": "x"}), _lambda_context())
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# GET /agents  (Requirement 1.2)
# ---------------------------------------------------------------------------

class TestGetAgents:
    def test_list_agents_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        handler(_apigw_event("POST", "/agents", body=_VALID_CARD), _lambda_context())
        resp = handler(_apigw_event("GET", "/agents"), _lambda_context())
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "items" in body
        assert "pagination" in body

    def test_list_agents_empty_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("GET", "/agents"), _lambda_context())
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["items"] == []
        assert body["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# GET /agents/search  (Requirement 2.1)
# ---------------------------------------------------------------------------

class TestGetAgentsSearch:
    def test_search_with_query_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(
            _apigw_event("GET", "/agents/search", query_params={"query": "trivia"}),
            _lambda_context(),
        )
        assert resp["statusCode"] == 200

    def test_search_missing_params_returns_400(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(
            _apigw_event("GET", "/agents/search", query_params={}),
            _lambda_context(),
        )
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error_code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# GET /agents/{agentId}  (Requirement 1.3)
# ---------------------------------------------------------------------------

class TestGetAgentById:
    def test_existing_agent_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        create_resp = handler(_apigw_event("POST", "/agents", body=_VALID_CARD), _lambda_context())
        agent_id = json.loads(create_resp["body"])["agent_id"]

        resp = handler(_apigw_event("GET", f"/agents/{agent_id}"), _lambda_context())
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["name"] == "TestAgent"

    def test_nonexistent_agent_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("GET", "/agents/nonexistent-id"), _lambda_context())
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error_code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# PUT /agents/{agentId}  (Requirement 1.4)
# ---------------------------------------------------------------------------

class TestPutAgent:
    def test_update_agent_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        create_resp = handler(_apigw_event("POST", "/agents", body=_VALID_CARD), _lambda_context())
        agent_id = json.loads(create_resp["body"])["agent_id"]

        updated = {"name": "Updated", "description": "New desc", "url": "https://new.com"}
        resp = handler(_apigw_event("PUT", f"/agents/{agent_id}", body=updated), _lambda_context())
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["message"] == "Agent updated successfully"

    def test_update_nonexistent_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        updated = {"name": "X", "description": "Y", "url": "https://z.com"}
        resp = handler(_apigw_event("PUT", "/agents/no-such-id", body=updated), _lambda_context())
        assert resp["statusCode"] == 404


# ---------------------------------------------------------------------------
# DELETE /agents/{agentId}  (Requirement 1.5)
# ---------------------------------------------------------------------------

class TestDeleteAgent:
    def test_delete_agent_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        create_resp = handler(_apigw_event("POST", "/agents", body=_VALID_CARD), _lambda_context())
        agent_id = json.loads(create_resp["body"])["agent_id"]

        resp = handler(_apigw_event("DELETE", f"/agents/{agent_id}"), _lambda_context())
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["message"] == "Agent deleted successfully"

        # Confirm it's gone
        get_resp = handler(_apigw_event("GET", f"/agents/{agent_id}"), _lambda_context())
        assert get_resp["statusCode"] == 404

    def test_delete_nonexistent_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("DELETE", "/agents/no-such-id"), _lambda_context())
        assert resp["statusCode"] == 404


# ---------------------------------------------------------------------------
# POST /agents/{agentId}/health  (Requirement 3.1)
# ---------------------------------------------------------------------------

class TestPostAgentHealth:
    def test_health_check_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        create_resp = handler(_apigw_event("POST", "/agents", body=_VALID_CARD), _lambda_context())
        agent_id = json.loads(create_resp["body"])["agent_id"]

        resp = handler(_apigw_event("POST", f"/agents/{agent_id}/health"), _lambda_context())
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["is_online"] is True
        assert body["agent_id"] == agent_id

    def test_health_nonexistent_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("POST", "/agents/no-such-id/health"), _lambda_context())
        assert resp["statusCode"] == 404


# ---------------------------------------------------------------------------
# POST /chat  (Requirement 4.1)
# ---------------------------------------------------------------------------

class TestPostChat:
    def test_chat_missing_fields_returns_400(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("POST", "/chat", body={}), _lambda_context())
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error_code"] == "VALIDATION_ERROR"

    def test_chat_nonexistent_agent_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(
            _apigw_event("POST", "/chat", body={"agentId": "no-such-id", "message": "hi"}),
            _lambda_context(),
        )
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error_code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Unknown routes → 404
# ---------------------------------------------------------------------------

class TestUnknownRoutes:
    def test_unknown_path_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("GET", "/unknown"), _lambda_context())
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert body["error_code"] == "NOT_FOUND"

    def test_unsupported_method_on_agents_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("PATCH", "/agents"), _lambda_context())
        assert resp["statusCode"] == 404

    def test_empty_path_returns_404(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("GET", "/"), _lambda_context())
        assert resp["statusCode"] == 404


# ---------------------------------------------------------------------------
# OPTIONS → 200 with CORS headers
# ---------------------------------------------------------------------------

class TestOptionsCors:
    def test_options_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("OPTIONS", "/agents"), _lambda_context())
        assert resp["statusCode"] == 200

    def test_options_includes_cors_headers(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("OPTIONS", "/agents"), _lambda_context())
        headers = resp["headers"]
        assert "Access-Control-Allow-Origin" in headers
        assert "Access-Control-Allow-Methods" in headers
        assert "Access-Control-Allow-Headers" in headers

    def test_options_on_any_path_returns_200(self, handler_and_store):
        handler, _ = handler_and_store
        resp = handler(_apigw_event("OPTIONS", "/chat"), _lambda_context())
        assert resp["statusCode"] == 200
