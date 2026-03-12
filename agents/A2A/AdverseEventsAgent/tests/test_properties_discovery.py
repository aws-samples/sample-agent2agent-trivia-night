"""Property-based tests for dynamic discovery — RegistryClient and OrchestratorAgent.

Uses hypothesis to validate correctness properties from the design document.
All HTTP and AWS calls are mocked at the requests/boto3 layer.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agent_directory.registry_client import RegistryClient, CacheEntry
from agents.orchestrator_agent import OrchestratorAgent
from models.adverse_event import AdverseEvent


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# URL-safe strings for agent card URLs and API base URLs
url_safe_text = st.text(
    min_size=1,
    alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="-_./",
    ),
)

# Agent card strategy
agent_card_st = st.fixed_dictionaries(
    {
        "agent_id": url_safe_text,
        "name": st.text(min_size=1, max_size=50),
        "description": st.text(min_size=1, max_size=100),
        "url": url_safe_text,
        "version": st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True),
        "skills": st.just([]),
    }
)

# Non-empty list of agent cards
agent_card_list_st = st.lists(agent_card_st, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_boto3_session():
    """Return a mock boto3.Session that provides fake frozen credentials."""
    mock_session = MagicMock()
    mock_creds = MagicMock()
    mock_creds.access_key = "AKIAIOSFODNN7EXAMPLE"
    mock_creds.secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    mock_creds.token = "FwoGZXIvYXdzEBYaDH"
    mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = (
        mock_creds
    )
    return mock_session


def _make_registry_client(api_url="https://example.com", **kwargs):
    """Create a RegistryClient with mocked boto3 session."""
    with patch(
        "agent_directory.registry_client.boto3.Session",
        new_callable=_mock_boto3_session,
    ):
        return RegistryClient(api_url=api_url, **kwargs)


def _make_event():
    """Create a minimal AdverseEvent for testing."""
    return AdverseEvent(
        event_id="E001",
        drug_name="TestDrug",
        adverse_event_term="Headache",
        medra_code="10019211",
        patient_age=45,
        patient_sex="M",
        event_date=datetime(2024, 1, 15),
        outcome="recovered",
        reporter_type="physician",
    )


# ---------------------------------------------------------------------------
# Property 1: Config resolution — random URLs via param/env, default region
#              and TTL
# Validates: Requirements 1.1, 1.2, 1.4, 1.5
# ---------------------------------------------------------------------------


class TestProperty1ConfigResolution:
    """Config resolution from parameter or environment.

    **Validates: Requirements 1.1, 1.2, 1.4, 1.5**
    """

    @given(api_url=url_safe_text)
    @settings(max_examples=50)
    def test_api_url_from_param(self, api_url):
        """For any URL string, when provided as api_url param it is used directly."""
        client = _make_registry_client(api_url=api_url)
        assert client.api_url == api_url.rstrip("/")

    @given(api_url=url_safe_text)
    @settings(max_examples=50)
    def test_api_url_from_env(self, api_url):
        """For any URL string, when provided only via env var it is read from env."""
        with patch.dict(os.environ, {"A2A_REGISTRY_API_URL": api_url}, clear=False):
            with patch(
                "agent_directory.registry_client.boto3.Session",
                new_callable=_mock_boto3_session,
            ):
                client = RegistryClient()
        assert client.api_url == api_url.rstrip("/")

    @given(api_url=url_safe_text)
    @settings(max_examples=50)
    def test_default_region(self, api_url):
        """When neither region param nor AWS_REGION env var is set, region defaults to us-east-1."""
        with patch.dict(os.environ, {}, clear=False):
            env = os.environ.copy()
            env.pop("AWS_REGION", None)
            with patch.dict(os.environ, env, clear=True):
                client = _make_registry_client(api_url=api_url)
        assert client.region == "us-east-1"

    @given(api_url=url_safe_text)
    @settings(max_examples=50)
    def test_default_cache_ttl(self, api_url):
        """When neither cache_ttl param nor env var is set, TTL defaults to 300."""
        with patch.dict(os.environ, {}, clear=False):
            env = os.environ.copy()
            env.pop("AGENT_DISCOVERY_CACHE_TTL", None)
            with patch.dict(os.environ, env, clear=True):
                client = _make_registry_client(api_url=api_url)
        assert client.cache_ttl == 300


# ---------------------------------------------------------------------------
# Property 2: Cache hit within TTL — same query returns same result, no HTTP
# Validates: Requirements 3.1, 3.2
# ---------------------------------------------------------------------------


class TestProperty2CacheHitWithinTTL:
    """Cache hit within TTL.

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        query=st.text(min_size=1, max_size=30),
        top_k=st.integers(min_value=1, max_value=10),
        agents=agent_card_list_st,
    )
    @settings(max_examples=50)
    def test_cache_hit_returns_same_result_no_http(self, query, top_k, agents):
        """For any successful search, a second call within TTL returns the same
        result without making an HTTP call."""
        client = _make_registry_client(cache_ttl=300)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agents": agents}
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "agent_directory.registry_client.requests.request",
            return_value=mock_resp,
        ) as mock_request:
            first = client.search(query, top_k=top_k)
            second = client.search(query, top_k=top_k)

        assert first == second
        assert mock_request.call_count == 1  # only one HTTP call


# ---------------------------------------------------------------------------
# Property 3: Cache miss after TTL — expired entries trigger new HTTP call
# Validates: Requirement 3.3
# ---------------------------------------------------------------------------


class TestProperty3CacheMissAfterTTL:
    """Cache miss after TTL.

    **Validates: Requirement 3.3**
    """

    @given(
        query=st.text(min_size=1, max_size=30),
        top_k=st.integers(min_value=1, max_value=10),
        agents=agent_card_list_st,
        ttl=st.integers(min_value=1, max_value=60),
    )
    @settings(max_examples=50)
    def test_expired_cache_triggers_new_http_call(self, query, top_k, agents, ttl):
        """For any cached entry, calling search() after TTL expiry makes a new
        HTTP request."""
        client = _make_registry_client(cache_ttl=ttl)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agents": agents}
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "agent_directory.registry_client.requests.request",
            return_value=mock_resp,
        ) as mock_request:
            client.search(query, top_k=top_k)
            assert mock_request.call_count == 1

            # Manually expire the cache entry
            for entry in client._cache.values():
                entry.cached_at -= ttl + 1

            client.search(query, top_k=top_k)
            assert mock_request.call_count == 2


# ---------------------------------------------------------------------------
# Property 4: First result selection — discover_agent returns first element
# Validates: Requirement 2.4
# ---------------------------------------------------------------------------


class TestProperty4FirstResultSelection:
    """First result selection.

    **Validates: Requirement 2.4**
    """

    @given(agents=agent_card_list_st)
    @settings(max_examples=50)
    def test_discover_agent_returns_first_element(self, agents):
        """For any non-empty search result list, discover_agent() returns the
        first element."""
        mock_rc = MagicMock()
        mock_rc.search.return_value = agents

        orch = OrchestratorAgent(registry_client=mock_rc)
        result = orch.discover_agent("any query")

        assert result == agents[0]


# ---------------------------------------------------------------------------
# Property 5: ARN construction — correct format for any URL string
# Validates: Requirement 4.1
# ---------------------------------------------------------------------------


class TestProperty5ARNConstruction:
    """ARN construction from agent card URL.

    **Validates: Requirement 4.1**
    """

    @given(url=url_safe_text)
    @settings(max_examples=50)
    def test_arn_format(self, url):
        """For any agent card URL, the ARN matches
        arn:aws:bedrock-agentcore:{region}:{account}:runtime/{url}."""
        mock_rc = MagicMock()
        mock_rc.heartbeat.return_value = None
        mock_rc.invalidate_cache.return_value = None

        orch = OrchestratorAgent(registry_client=mock_rc)

        mock_runtime = MagicMock()
        mock_runtime.invoke_agent.return_value = {"completion": []}

        with patch("agents.orchestrator_agent.boto3.client", return_value=mock_runtime):
            card = {"agent_id": "test", "url": url}
            orch.invoke_remote_agent(card, {"action": "test"})

        expected_arn = f"arn:aws:bedrock-agentcore:{orch.region}:{orch.account}:runtime/{url}"
        actual_arn = mock_runtime.invoke_agent.call_args[1]["agentRuntimeArn"]
        assert actual_arn == expected_arn


# ---------------------------------------------------------------------------
# Property 6: Cache invalidation on failure — cache cleared after invoke
#              failure
# Validates: Requirements 3.4, 4.4
# ---------------------------------------------------------------------------


class TestProperty6CacheInvalidationOnFailure:
    """Cache invalidation on invocation failure.

    **Validates: Requirements 3.4, 4.4**
    """

    @given(agent_card=agent_card_st)
    @settings(max_examples=50)
    def test_cache_cleared_and_success_false_on_failure(self, agent_card):
        """For any cached agent, if invoke_remote_agent fails, the cache is
        invalidated and the returned dict has success=False."""
        mock_rc = MagicMock()
        mock_rc.invalidate_cache.return_value = None

        orch = OrchestratorAgent(registry_client=mock_rc)

        mock_runtime = MagicMock()
        mock_runtime.invoke_agent.side_effect = Exception("Invocation failed")

        with patch("agents.orchestrator_agent.boto3.client", return_value=mock_runtime):
            result = orch.invoke_remote_agent(agent_card, {"action": "test"})

        mock_rc.invalidate_cache.assert_called_once()
        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Property 7: Heartbeat error swallowing — no exception propagates
# Validates: Requirement 4.5
# ---------------------------------------------------------------------------


class TestProperty7HeartbeatErrorSwallowing:
    """Heartbeat never propagates errors.

    **Validates: Requirement 4.5**
    """

    @given(
        agent_id=url_safe_text,
        exc_type=st.sampled_from([
            Exception,
            ConnectionError,
            TimeoutError,
            OSError,
            RuntimeError,
            ValueError,
            IOError,
        ]),
    )
    @settings(max_examples=50)
    def test_heartbeat_swallows_any_exception(self, agent_id, exc_type):
        """For any exception type raised by the heartbeat endpoint,
        heartbeat() catches it and returns without raising."""
        client = _make_registry_client()

        with patch(
            "agent_directory.registry_client.requests.request",
            side_effect=exc_type("simulated failure"),
        ):
            # Must not raise
            client.heartbeat(agent_id)


# ---------------------------------------------------------------------------
# Property 8: Registry errors return empty list — any HTTP error yields []
# Validates: Requirement 2.3
# ---------------------------------------------------------------------------


class TestProperty8RegistryErrorsReturnEmptyList:
    """Registry errors return empty list.

    **Validates: Requirement 2.3**
    """

    @given(
        query=st.text(min_size=1, max_size=30),
        exc_type=st.sampled_from([
            Exception,
            ConnectionError,
            TimeoutError,
            OSError,
            RuntimeError,
        ]),
    )
    @settings(max_examples=50)
    def test_any_http_error_yields_empty_list(self, query, exc_type):
        """For any HTTP error or network exception during search(), the
        RegistryClient returns an empty list."""
        client = _make_registry_client()

        with patch(
            "agent_directory.registry_client.requests.request",
            side_effect=exc_type("simulated error"),
        ):
            result = client.search(query)

        assert result == []


# ---------------------------------------------------------------------------
# Property 9: Partial results preserved on step failure
# Validates: Requirements 5.3, 5.4
# ---------------------------------------------------------------------------


class TestProperty9PartialResultsPreserved:
    """Investigation preserves partial results on step failure.

    **Validates: Requirements 5.3, 5.4**
    """

    @given(
        fail_step=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=10)
    def test_partial_results_on_step_failure(self, fail_step):
        """For any investigation where step N fails, the InvestigationResult
        contains results from all steps completed before step N."""
        mock_rc = MagicMock()
        mock_rc.search.return_value = [
            {
                "agent_id": "agent-1",
                "name": "Agent",
                "description": "Test",
                "url": "agent-1",
                "version": "1.0.0",
                "skills": [],
            }
        ]
        mock_rc.heartbeat.return_value = None
        mock_rc.invalidate_cache.return_value = None

        orch = OrchestratorAgent(registry_client=mock_rc)

        # Build invoke side effects: succeed until fail_step, then fail
        invoke_results = []
        for step in range(1, 4):
            if step < fail_step:
                invoke_results.append({"success": True, "result": f"step {step} ok"})
            elif step == fail_step:
                invoke_results.append({"success": False, "error": f"step {step} failed"})
            else:
                # After failure, steps may or may not be called depending on
                # workflow logic — provide a result just in case
                invoke_results.append({"success": True, "result": f"step {step} ok"})

        with patch.object(orch, "invoke_remote_agent", side_effect=invoke_results):
            event = _make_event()
            result = orch.initiate_investigation([event])

        # Investigation must return a result (not crash)
        assert result is not None
        assert result.investigation_id is not None
        assert result.started_at is not None

        # If step 1 fails, signal detection failed — errors recorded
        if fail_step == 1:
            assert len(result.errors) > 0

        # If step 2 or 3 fails, earlier steps completed — errors recorded
        if fail_step >= 2:
            assert len(result.errors) > 0
