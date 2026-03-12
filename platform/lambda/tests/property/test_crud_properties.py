"""
Property-based tests for Agent CRUD operations, pagination, and health checks.

Tests exercise the ``lambda_handler`` function directly by constructing
API Gateway proxy events and asserting on the response structure.  All
external dependencies (S3 Vectors, Bedrock) are mocked at the service level.

Uses ``hypothesis`` with a minimum of 100 examples per property.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

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
    """Build a minimal API Gateway Lambda proxy event."""
    event: Dict[str, Any] = {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": query_params,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"requestId": request_id},
        "pathParameters": None,
        "isBase64Encoded": False,
    }
    return event


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

# Non-empty printable text (avoids null bytes that break JSON round-trips)
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z"), blacklist_characters="\x00"),
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

        # Re-import to pick up mocks (handler creates singletons at import)
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
# Property 1: Agent CRUD Round Trip
# Feature: lss-workshop-platform, Property 1: Agent CRUD Round Trip
# ---------------------------------------------------------------------------

class TestAgentCRUDRoundTrip:
    """**Validates: Requirements 1.1, 1.3**

    For any valid Agent_Card with random name, description, url, and skills,
    creating the agent via POST /agents and then retrieving it via
    GET /agents/{agentId} should return an agent card whose name, description,
    url, and skills match the original input.
    """

    @given(card=_agent_card_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_create_then_get_returns_matching_fields(self, card: Dict[str, Any]) -> None:
        # Feature: lss-workshop-platform, Property 1: Agent CRUD Round Trip
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # CREATE
        create_resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
        assert create_resp["statusCode"] == 201, (
            f"Expected 201, got {create_resp['statusCode']}: {create_resp['body']}"
        )
        create_body = json.loads(create_resp["body"])
        agent_id = create_body["agent_id"]

        # GET
        get_resp = handler(_apigw_event("GET", f"/agents/{agent_id}"), ctx)
        assert get_resp["statusCode"] == 200, (
            f"Expected 200, got {get_resp['statusCode']}: {get_resp['body']}"
        )
        agent = json.loads(get_resp["body"])

        # Assert round-trip equality
        assert agent["name"] == card["name"]
        assert agent["description"] == card["description"]
        assert agent["url"] == card["url"]

        # Skills: compare by name set (metadata stores skill names)
        input_skill_names = {s["name"] for s in card.get("skills", [])}
        returned_skills = agent.get("skills", [])
        if isinstance(returned_skills, list) and returned_skills and isinstance(returned_skills[0], dict):
            returned_skill_names = {s.get("name", "") for s in returned_skills}
        elif isinstance(returned_skills, list):
            returned_skill_names = set(returned_skills)
        else:
            returned_skill_names = set()
        assert input_skill_names == returned_skill_names


# ---------------------------------------------------------------------------
# Property 2: Agent Update Round Trip
# Feature: lss-workshop-platform, Property 2: Agent Update Round Trip
# ---------------------------------------------------------------------------

class TestAgentUpdateRoundTrip:
    """**Validates: Requirements 1.4**

    For any existing agent and any valid updated Agent_Card fields, updating
    via PUT /agents/{agentId} and then retrieving via GET /agents/{agentId}
    should return the updated field values.
    """

    @given(
        original=_agent_card_strategy,
        updated=_agent_card_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_update_then_get_returns_updated_fields(
        self, original: Dict[str, Any], updated: Dict[str, Any]
    ) -> None:
        # Feature: lss-workshop-platform, Property 2: Agent Update Round Trip
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # CREATE
        create_resp = handler(_apigw_event("POST", "/agents", body=original), ctx)
        assert create_resp["statusCode"] == 201
        agent_id = json.loads(create_resp["body"])["agent_id"]

        # UPDATE
        update_resp = handler(
            _apigw_event("PUT", f"/agents/{agent_id}", body=updated), ctx
        )
        assert update_resp["statusCode"] == 200, (
            f"Expected 200, got {update_resp['statusCode']}: {update_resp['body']}"
        )

        # GET
        get_resp = handler(_apigw_event("GET", f"/agents/{agent_id}"), ctx)
        assert get_resp["statusCode"] == 200
        agent = json.loads(get_resp["body"])

        assert agent["name"] == updated["name"]
        assert agent["description"] == updated["description"]
        assert agent["url"] == updated["url"]


# ---------------------------------------------------------------------------
# Property 3: Agent Deletion Removes Agent
# Feature: lss-workshop-platform, Property 3: Agent Deletion Removes Agent
# ---------------------------------------------------------------------------

class TestAgentDeletionRemovesAgent:
    """**Validates: Requirements 1.5**

    For any existing agent, after calling DELETE /agents/{agentId}, a
    subsequent GET /agents/{agentId} should return a 404 status code.
    """

    @given(card=_agent_card_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_delete_then_get_returns_404(self, card: Dict[str, Any]) -> None:
        # Feature: lss-workshop-platform, Property 3: Agent Deletion Removes Agent
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # CREATE
        create_resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
        assert create_resp["statusCode"] == 201
        agent_id = json.loads(create_resp["body"])["agent_id"]

        # DELETE
        del_resp = handler(_apigw_event("DELETE", f"/agents/{agent_id}"), ctx)
        assert del_resp["statusCode"] == 200

        # GET should 404
        get_resp = handler(_apigw_event("GET", f"/agents/{agent_id}"), ctx)
        assert get_resp["statusCode"] == 404, (
            f"Expected 404 after deletion, got {get_resp['statusCode']}"
        )
        error_body = json.loads(get_resp["body"])
        assert error_body["error_code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Property 4: Non-Existent Agent Returns 404
# Feature: lss-workshop-platform, Property 4: Non-Existent Agent Returns 404
# ---------------------------------------------------------------------------

class TestNonExistentAgentReturns404:
    """**Validates: Requirements 1.6, 3.3, 4.5**

    For any randomly generated UUID that does not correspond to a registered
    agent, calling GET /agents/{agentId}, POST /agents/{agentId}/health, or
    POST /chat with that agent ID should return a 404 status code with an
    error message containing the agent ID.
    """

    @given(random_id=st.uuids().map(str))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_get_nonexistent_agent_returns_404(self, random_id: str) -> None:
        # Feature: lss-workshop-platform, Property 4: Non-Existent Agent Returns 404
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # GET /agents/{agentId}
        get_resp = handler(_apigw_event("GET", f"/agents/{random_id}"), ctx)
        assert get_resp["statusCode"] == 404
        body = json.loads(get_resp["body"])
        assert body["error_code"] == "NOT_FOUND"
        assert random_id in body["message"]

    @given(random_id=st.uuids().map(str))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_health_nonexistent_agent_returns_404(self, random_id: str) -> None:
        # Feature: lss-workshop-platform, Property 4: Non-Existent Agent Returns 404
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # POST /agents/{agentId}/health
        health_resp = handler(
            _apigw_event("POST", f"/agents/{random_id}/health"), ctx
        )
        assert health_resp["statusCode"] == 404
        body = json.loads(health_resp["body"])
        assert body["error_code"] == "NOT_FOUND"
        assert random_id in body["message"]

    @given(random_id=st.uuids().map(str))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_chat_nonexistent_agent_returns_404(self, random_id: str) -> None:
        # Feature: lss-workshop-platform, Property 4: Non-Existent Agent Returns 404
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # POST /chat with non-existent agentId
        chat_resp = handler(
            _apigw_event("POST", "/chat", body={"agentId": random_id, "message": "hello"}),
            ctx,
        )
        assert chat_resp["statusCode"] == 404
        body = json.loads(chat_resp["body"])
        assert body["error_code"] == "NOT_FOUND"
        assert random_id in body["message"]


# ---------------------------------------------------------------------------
# Property 5: Invalid Agent Card Rejected
# Feature: lss-workshop-platform, Property 5: Invalid Agent Card Rejected
# ---------------------------------------------------------------------------

# Strategy that produces agent cards with at least one required field missing
_required_fields = ["name", "description", "url"]

_invalid_card_strategy = st.fixed_dictionaries({
    "name": st.one_of(st.just(None), st.just(""), _safe_text),
    "description": st.one_of(st.just(None), st.just(""), _safe_text),
    "url": st.one_of(st.just(None), st.just(""), _safe_text),
    "skills": st.lists(_skill_strategy, min_size=0, max_size=3),
}).filter(
    # Keep only cards where at least one required field is missing/empty
    lambda c: any(
        not isinstance(c.get(f), str) or not c[f].strip()
        for f in _required_fields
    )
).map(
    # Remove None values so the JSON body looks realistic
    lambda c: {k: v for k, v in c.items() if v is not None}
)


class TestInvalidAgentCardRejected:
    """**Validates: Requirements 1.7, 14.1**

    For any JSON body that is missing one or more of the required Agent_Card
    fields (name, description, url), POST /agents should return a 400 status
    code with a VALIDATION_ERROR error code.
    """

    @given(card=_invalid_card_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_required_fields_returns_400(self, card: Dict[str, Any]) -> None:
        # Feature: lss-workshop-platform, Property 5: Invalid Agent Card Rejected
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
        assert resp["statusCode"] == 400, (
            f"Expected 400 for invalid card {card}, got {resp['statusCode']}: {resp['body']}"
        )
        body = json.loads(resp["body"])
        assert body["error_code"] == "VALIDATION_ERROR"
        assert "message" in body


# ---------------------------------------------------------------------------
# Property 6: Pagination Returns Correct Subset
# Feature: lss-workshop-platform, Property 6: Pagination Returns Correct Subset
# ---------------------------------------------------------------------------

class TestPaginationReturnsCorrectSubset:
    """**Validates: Requirements 1.2**

    For any set of N registered agents and any valid limit and offset
    parameters where offset < N, GET /agents?limit=L&offset=O should return
    at most L agents, pagination.total should equal N, and
    pagination.has_more should be true iff O + len(items) < N.
    """

    @given(
        cards=st.lists(_agent_card_strategy, min_size=1, max_size=10),
        data=st.data(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_pagination_subset(
        self, cards: List[Dict[str, Any]], data: st.DataObject
    ) -> None:
        # Feature: lss-workshop-platform, Property 6: Pagination Returns Correct Subset
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        n = len(cards)

        # Create all agents
        for card in cards:
            resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
            assert resp["statusCode"] == 201

        # Draw random limit and offset
        limit = data.draw(st.integers(min_value=1, max_value=n + 5))
        offset = data.draw(st.integers(min_value=0, max_value=n - 1))

        list_resp = handler(
            _apigw_event(
                "GET",
                "/agents",
                query_params={"limit": str(limit), "offset": str(offset)},
            ),
            ctx,
        )
        assert list_resp["statusCode"] == 200
        body = json.loads(list_resp["body"])

        items = body["items"]
        pagination = body["pagination"]

        # At most `limit` items returned
        assert len(items) <= limit

        # Total equals number of created agents
        assert pagination["total"] == n

        # has_more correctness
        expected_has_more = (offset + len(items)) < n
        assert pagination["has_more"] == expected_has_more


# ---------------------------------------------------------------------------
# Property 9: Health Check Updates Timestamp
# Feature: lss-workshop-platform, Property 9: Health Check Updates Timestamp
# ---------------------------------------------------------------------------

class TestHealthCheckUpdatesTimestamp:
    """**Validates: Requirements 3.1, 3.2**

    For any registered agent, calling POST /agents/{agentId}/health should
    update the agent's last_health_check timestamp to a value within a
    reasonable delta of the current time, and set is_online to true.
    """

    @given(card=_agent_card_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_health_check_sets_online_and_timestamp(self, card: Dict[str, Any]) -> None:
        # Feature: lss-workshop-platform, Property 9: Health Check Updates Timestamp
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # CREATE
        create_resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
        assert create_resp["statusCode"] == 201
        agent_id = json.loads(create_resp["body"])["agent_id"]

        # Record time before health check
        before = datetime.now(timezone.utc)

        # HEALTH CHECK
        health_resp = handler(
            _apigw_event("POST", f"/agents/{agent_id}/health"), ctx
        )
        assert health_resp["statusCode"] == 200

        after = datetime.now(timezone.utc)

        health_body = json.loads(health_resp["body"])
        assert health_body["is_online"] is True
        assert health_body["agent_id"] == agent_id

        # Verify timestamp is within a reasonable window
        ts = datetime.fromisoformat(health_body["last_health_check"])
        # Allow 5 seconds of tolerance
        assert before - timedelta(seconds=5) <= ts <= after + timedelta(seconds=5), (
            f"Timestamp {ts} not within expected range [{before}, {after}]"
        )

        # Verify GET also reflects the updated health status
        get_resp = handler(_apigw_event("GET", f"/agents/{agent_id}"), ctx)
        assert get_resp["statusCode"] == 200
        agent = json.loads(get_resp["body"])
        assert agent["is_online"] is True
