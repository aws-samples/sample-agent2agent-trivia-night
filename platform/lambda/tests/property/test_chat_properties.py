"""
Property-based tests for Chat endpoint operations.

Tests exercise the ``lambda_handler`` function directly by constructing
API Gateway proxy events and asserting on the response structure.  All
external dependencies (S3 Vectors, Bedrock, MCP) are mocked at the service
level.

Uses ``hypothesis`` with a minimum of 100 examples per property.
"""
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers (reused from test_crud_properties)
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
# Hypothesis strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())

_skill_strategy = st.fixed_dictionaries({
    "id": st.uuids().map(str),
    "name": _safe_text,
    "description": _safe_text,
})

_agent_card_strategy = st.fixed_dictionaries({
    "name": _safe_text,
    "description": _safe_text,
    "url": _safe_text,
    "skills": st.lists(_skill_strategy, min_size=0, max_size=5),
})


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


def _fake_embedding(text: str) -> List[float]:
    """Return a deterministic 1024-dim fake embedding."""
    return [0.1] * 1024


# ---------------------------------------------------------------------------
# Handler builder with MCP mocking for chat tests
# ---------------------------------------------------------------------------

def _build_patched_handler(store: _InMemoryVectorStore, mock_agent_response: str = "Hello from agent"):
    """Import handler with mocked S3 Vectors, Bedrock, and MCP clients.

    The MCP ``streamablehttp_client`` and ``ClientSession`` are patched so
    that chat invocations return *mock_agent_response* without any network
    calls.
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

    # Build a mock MCP tool result content block
    mock_text_block = MagicMock()
    mock_text_block.text = mock_agent_response

    mock_tool_result = MagicMock()
    mock_tool_result.content = [mock_text_block]

    # Mock tool listing — one tool named "invoke"
    mock_tool = MagicMock()
    mock_tool.name = "invoke"
    mock_tools_result = MagicMock()
    mock_tools_result.tools = [mock_tool]

    # Build async mock session
    mock_session_instance = AsyncMock()
    mock_session_instance.initialize = AsyncMock()
    mock_session_instance.list_tools = AsyncMock(return_value=mock_tools_result)
    mock_session_instance.call_tool = AsyncMock(return_value=mock_tool_result)

    # Make the session usable as an async context manager
    mock_session_cls = MagicMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session_instance)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session_cls.return_value = mock_session_cm

    # Build async context manager for streamablehttp_client
    mock_transport_cm = AsyncMock()
    mock_read_stream = AsyncMock()
    mock_write_stream = AsyncMock()
    mock_transport_cm.__aenter__ = AsyncMock(
        return_value=(mock_read_stream, mock_write_stream, None)
    )
    mock_transport_cm.__aexit__ = AsyncMock(return_value=False)
    mock_streamable_fn = MagicMock(return_value=mock_transport_cm)

    with patch("services.agent_service.boto3") as mock_boto_agent, \
         patch("services.health_service.boto3") as mock_boto_health, \
         patch("services.embedding_service.boto3") as mock_boto_embed, \
         patch("services.chat_service.streamablehttp_client", mock_streamable_fn), \
         patch("services.chat_service.ClientSession", mock_session_cls):

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


def _setup_handler(mock_agent_response: str = "Hello from agent"):
    """Create a fresh in-memory store and return (handler, store)."""
    store = _InMemoryVectorStore()
    handler = _build_patched_handler(store, mock_agent_response=mock_agent_response)
    return handler, store


# ---------------------------------------------------------------------------
# Property 10: Chat Response Contains Required Fields
# Feature: lss-workshop-platform, Property 10: Chat Response Contains Required Fields
# ---------------------------------------------------------------------------

class TestChatResponseContainsRequiredFields:
    """**Validates: Requirements 4.4**

    For any successful chat invocation (where the agent is reachable), the
    response JSON should contain non-empty agentId, response, and agentName
    string fields.
    """

    @given(card=_agent_card_strategy, message=_safe_text)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_chat_response_has_required_fields(
        self, card: Dict[str, Any], message: str
    ) -> None:
        # Feature: lss-workshop-platform, Property 10: Chat Response Contains Required Fields
        mock_response = "This is the agent response"
        handler, _store = _setup_handler(mock_agent_response=mock_response)
        ctx = _lambda_context()

        # Create an agent first
        create_resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
        assert create_resp["statusCode"] == 201
        agent_id = json.loads(create_resp["body"])["agent_id"]

        # POST /chat
        chat_resp = handler(
            _apigw_event("POST", "/chat", body={"agentId": agent_id, "message": message}),
            ctx,
        )
        assert chat_resp["statusCode"] == 200, (
            f"Expected 200, got {chat_resp['statusCode']}: {chat_resp['body']}"
        )
        body = json.loads(chat_resp["body"])

        # Verify required fields are present and non-empty strings
        assert isinstance(body.get("agentId"), str) and body["agentId"].strip(), (
            f"agentId should be a non-empty string, got: {body.get('agentId')!r}"
        )
        assert isinstance(body.get("response"), str) and body["response"].strip(), (
            f"response should be a non-empty string, got: {body.get('response')!r}"
        )
        assert isinstance(body.get("agentName"), str) and body["agentName"].strip(), (
            f"agentName should be a non-empty string, got: {body.get('agentName')!r}"
        )

        # agentId in response should match the one we sent
        assert body["agentId"] == agent_id


# ---------------------------------------------------------------------------
# Property 11: Missing Chat Fields Rejected
# Feature: lss-workshop-platform, Property 11: Missing Chat Fields Rejected
# ---------------------------------------------------------------------------

# Strategy: generate chat requests where agentId is missing/empty OR message
# is missing/empty (or both).  We use a composite strategy that randomly
# omits or empties one or both required fields.

_empty_or_missing = st.one_of(
    st.just(None),       # field missing (will be removed from dict)
    st.just(""),         # empty string
    st.just("   "),      # whitespace-only
)

_valid_field = _safe_text  # guaranteed non-empty, non-whitespace

_invalid_chat_request_strategy = st.fixed_dictionaries({
    "agentId": st.one_of(_empty_or_missing, _valid_field),
    "message": st.one_of(_empty_or_missing, _valid_field),
}).filter(
    # Keep only requests where at least one required field is missing/empty
    lambda r: (
        r.get("agentId") is None
        or (isinstance(r.get("agentId"), str) and not r["agentId"].strip())
        or r.get("message") is None
        or (isinstance(r.get("message"), str) and not r["message"].strip())
    )
).map(
    # Remove None values so the JSON body looks realistic (field absent)
    lambda r: {k: v for k, v in r.items() if v is not None}
)


class TestMissingChatFieldsRejected:
    """**Validates: Requirements 4.6, 14.2**

    For any POST /chat request where agentId is missing/empty or message is
    missing/empty, the API should return a 400 status code with a
    VALIDATION_ERROR error code.
    """

    @given(chat_body=_invalid_chat_request_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_or_empty_fields_returns_400(
        self, chat_body: Dict[str, Any]
    ) -> None:
        # Feature: lss-workshop-platform, Property 11: Missing Chat Fields Rejected
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        resp = handler(_apigw_event("POST", "/chat", body=chat_body), ctx)
        assert resp["statusCode"] == 400, (
            f"Expected 400 for chat body {chat_body}, got {resp['statusCode']}: {resp['body']}"
        )
        body = json.loads(resp["body"])
        assert body["error_code"] == "VALIDATION_ERROR", (
            f"Expected VALIDATION_ERROR, got {body.get('error_code')!r}"
        )
        assert "message" in body
