"""
Property-based tests for Agent Search operations.

Tests exercise the ``lambda_handler`` function directly by constructing
API Gateway proxy events and asserting on the response structure.  All
external dependencies (S3 Vectors, Bedrock) are mocked at the service level.

Uses ``hypothesis`` with a minimum of 100 examples per property.
"""
import json
import random
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers (reused patterns from test_crud_properties.py)
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
# In-memory vector store mock (extended with search support)
# ---------------------------------------------------------------------------


class _InMemoryVectorStore:
    """Minimal in-memory replacement for the S3 Vectors client.

    Extended from the CRUD version to support ``query_vectors`` that returns
    stored vectors with synthetic distances, enabling search property tests.
    """

    def __init__(self) -> None:
        self.vectors: Dict[str, Dict[str, Any]] = {}
        self._distance_counter: float = 0.0

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
        """Return all stored vectors with distinct ascending distances.

        Each vector gets a unique distance so the search service can sort
        them into a deterministic descending-similarity order.
        """
        results = []
        distance = 0.05
        for vec in self.vectors.values():
            results.append({
                "key": vec["key"],
                "metadata": vec["metadata"],
                "distance": round(distance, 6),
            })
            distance += 0.1
        return {"vectors": results}


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

    with (
        patch("services.agent_service.boto3") as mock_boto_agent,
        patch("services.health_service.boto3") as mock_boto_health,
        patch("services.embedding_service.boto3") as mock_boto_embed,
        patch("services.chat_service.AgentService") as mock_chat_as,
        patch("services.search_service.boto3") as mock_boto_search,
    ):
        mock_boto_agent.client.return_value = mock_s3v
        mock_boto_health.client.return_value = mock_s3v
        mock_boto_embed.client.return_value = mock_bedrock
        mock_boto_search.client.return_value = mock_s3v

        # Re-import to pick up mocks (handler creates singletons at import)
        import importlib
        import services.embedding_service as embed_mod
        importlib.reload(embed_mod)
        import services.agent_service as agent_mod
        importlib.reload(agent_mod)
        import services.health_service as health_mod
        importlib.reload(health_mod)
        import services.search_service as search_mod
        importlib.reload(search_mod)
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
# Property 7: Search Results Ranked by Similarity
# Feature: lss-workshop-platform, Property 7: Search Results Ranked by Similarity
# ---------------------------------------------------------------------------


class TestSearchResultsRankedBySimilarity:
    """**Validates: Requirements 2.3**

    For any search query against a registry containing multiple agents, the
    returned results should be sorted by similarity_score in descending order
    (i.e., for consecutive results i and i+1,
    results[i].similarity_score >= results[i+1].similarity_score).
    """

    @given(
        cards=st.lists(_agent_card_strategy, min_size=2, max_size=8),
        query=_safe_text,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_search_results_sorted_descending_by_similarity(
        self, cards: List[Dict[str, Any]], query: str
    ) -> None:
        # Feature: lss-workshop-platform, Property 7: Search Results Ranked by Similarity
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # Register all agents
        for card in cards:
            resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
            assert resp["statusCode"] == 201, (
                f"Expected 201, got {resp['statusCode']}: {resp['body']}"
            )

        # Search
        search_resp = handler(
            _apigw_event(
                "GET",
                "/agents/search",
                query_params={"query": query},
            ),
            ctx,
        )
        assert search_resp["statusCode"] == 200, (
            f"Expected 200, got {search_resp['statusCode']}: {search_resp['body']}"
        )
        body = json.loads(search_resp["body"])
        results = body["results"]

        # Verify descending similarity_score order
        for i in range(len(results) - 1):
            assert results[i]["similarity_score"] >= results[i + 1]["similarity_score"], (
                f"Results not sorted: index {i} score "
                f"{results[i]['similarity_score']} < index {i+1} score "
                f"{results[i+1]['similarity_score']}"
            )


# ---------------------------------------------------------------------------
# Property 8: Skills Filter Returns Matching Agents
# Feature: lss-workshop-platform, Property 8: Skills Filter Returns Matching Agents
# ---------------------------------------------------------------------------


class TestSkillsFilterReturnsMatchingAgents:
    """**Validates: Requirements 2.4**

    For any set of registered agents with known skills and any non-empty
    skills filter, all agents in the search results should have at least one
    skill whose name overlaps with the filter skills.
    """

    @given(
        cards=st.lists(_agent_card_strategy, min_size=1, max_size=8),
        data=st.data(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_skills_filter_returns_only_matching_agents(
        self, cards: List[Dict[str, Any]], data: st.DataObject
    ) -> None:
        # Feature: lss-workshop-platform, Property 8: Skills Filter Returns Matching Agents
        handler, _store = _setup_handler()
        ctx = _lambda_context()

        # Register all agents and collect their skill names
        all_skill_names: List[str] = []
        for card in cards:
            resp = handler(_apigw_event("POST", "/agents", body=card), ctx)
            assert resp["statusCode"] == 201
            for skill in card.get("skills", []):
                name = skill.get("name", "").strip()
                if name:
                    all_skill_names.append(name)

        # We need at least one skill across all agents to form a filter
        assume(len(all_skill_names) > 0)

        # Draw a non-empty subset of existing skill names as the filter
        filter_skills = data.draw(
            st.lists(
                st.sampled_from(all_skill_names),
                min_size=1,
                max_size=min(3, len(all_skill_names)),
            )
        )
        filter_skills_csv = ",".join(filter_skills)
        filter_skills_lower = {s.lower() for s in filter_skills}

        # Search with skills filter (also need a query for the endpoint)
        search_resp = handler(
            _apigw_event(
                "GET",
                "/agents/search",
                query_params={"query": "agent", "skills": filter_skills_csv},
            ),
            ctx,
        )
        assert search_resp["statusCode"] == 200, (
            f"Expected 200, got {search_resp['statusCode']}: {search_resp['body']}"
        )
        body = json.loads(search_resp["body"])
        results = body["results"]

        # Every returned agent must have at least one skill overlapping
        # with the filter skills (case-insensitive)
        for result in results:
            agent_card = result["agent_card"]
            agent_skills_raw = agent_card.get("skills", [])

            # Skills may be stored as list of dicts or list of strings
            if agent_skills_raw and isinstance(agent_skills_raw[0], dict):
                agent_skill_names = {
                    s.get("name", "").lower() for s in agent_skills_raw
                }
            else:
                agent_skill_names = {
                    str(s).lower() for s in agent_skills_raw
                }

            overlap = agent_skill_names & filter_skills_lower
            assert len(overlap) > 0, (
                f"Agent {result['agent_id']} has skills {agent_skill_names} "
                f"but none overlap with filter {filter_skills_lower}"
            )
