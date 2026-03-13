"""Unit tests for RegistryClient — A2A Agent Registry API client with SigV4 auth and TTL caching."""

import os
import time
from unittest.mock import patch, MagicMock

import pytest

from agent_directory.registry_client import RegistryClient, CacheEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_boto3_session():
    """Return a mock boto3.Session that provides fake frozen credentials."""
    mock_session = MagicMock()
    mock_creds = MagicMock()
    mock_creds.access_key = "AKIAIOSFODNN7EXAMPLE"
    mock_creds.secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # nosec B105
    mock_creds.token = "FwoGZXIvYXdzEBYaDH"  # nosec B105
    mock_session.return_value.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
    return mock_session


SAMPLE_AGENTS = [
    {
        "agent_id": "signal_detection-Rb6ez2HHzC",
        "name": "Signal Detection Agent",
        "description": "Analyzes adverse event reports",
        "url": "signal_detection-Rb6ez2HHzC",
        "version": "1.0.0",
        "skills": [],
    },
    {
        "agent_id": "literature_mining-JSgVgH7UsS",
        "name": "Literature Mining Agent",
        "description": "Searches medical literature",
        "url": "literature_mining-JSgVgH7UsS",
        "version": "1.0.0",
        "skills": [],
    },
]

API_URL = "https://b07qlmpb6b.execute-api.us-east-1.amazonaws.com"


# ---------------------------------------------------------------------------
# Configuration tests (Requirement 1)
# ---------------------------------------------------------------------------

class TestRegistryClientConfig:
    """Tests for RegistryClient configuration resolution."""

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    def test_config_from_param(self, _mock_session):
        """api_url param is used directly when provided."""
        client = RegistryClient(api_url=API_URL)
        assert client.api_url == API_URL

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch.dict(os.environ, {"A2A_REGISTRY_API_URL": API_URL}, clear=False)
    def test_config_from_env_var(self, _mock_session):
        """Falls back to A2A_REGISTRY_API_URL env var when param is omitted."""
        client = RegistryClient()
        assert client.api_url == API_URL

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_url_raises_value_error(self, _mock_session):
        """ValueError raised when neither param nor env var provides a URL."""
        with pytest.raises(ValueError, match="api_url must be provided"):
            RegistryClient()

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    def test_default_region(self, _mock_session):
        """Region defaults to us-east-1 when not provided."""
        client = RegistryClient(api_url=API_URL)
        assert client.region == "us-east-1"

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}, clear=False)
    def test_region_from_env(self, _mock_session):
        """Region read from AWS_REGION env var."""
        client = RegistryClient(api_url=API_URL)
        assert client.region == "eu-west-1"

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    def test_default_cache_ttl(self, _mock_session):
        """Cache TTL defaults to 300 seconds."""
        client = RegistryClient(api_url=API_URL)
        assert client.cache_ttl == 300

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch.dict(os.environ, {"AGENT_DISCOVERY_CACHE_TTL": "60"}, clear=False)
    def test_cache_ttl_from_env(self, _mock_session):
        """Cache TTL read from AGENT_DISCOVERY_CACHE_TTL env var."""
        client = RegistryClient(api_url=API_URL)
        assert client.cache_ttl == 60

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    def test_cache_ttl_from_param(self, _mock_session):
        """Cache TTL from constructor param takes precedence."""
        client = RegistryClient(api_url=API_URL, cache_ttl=120)
        assert client.cache_ttl == 120


# ---------------------------------------------------------------------------
# Search tests (Requirement 2)
# ---------------------------------------------------------------------------

class TestRegistryClientSearch:
    """Tests for RegistryClient.search() — semantic agent discovery."""

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_search_sends_correct_url_and_params(self, mock_request, _mock_session):
        """search() sends SigV4-signed GET to /agents/search with query and top_k."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agents": SAMPLE_AGENTS}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        client = RegistryClient(api_url=API_URL)
        client.search("detect safety signals", top_k=5)

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == f"{API_URL}/agents/search"
        assert call_args[1]["params"] == {"query": "detect safety signals", "top_k": 5}

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_search_returns_agent_cards(self, mock_request, _mock_session):
        """search() returns list of agent card dicts from the API response."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agents": SAMPLE_AGENTS}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        client = RegistryClient(api_url=API_URL)
        results = client.search("detect safety signals")

        assert results == SAMPLE_AGENTS
        assert len(results) == 2

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_search_returns_empty_list_on_error(self, mock_request, _mock_session):
        """search() returns [] and logs warning on HTTP error."""
        mock_request.side_effect = Exception("Connection refused")

        client = RegistryClient(api_url=API_URL)
        results = client.search("detect safety signals")

        assert results == []


# ---------------------------------------------------------------------------
# Cache tests (Requirement 3)
# ---------------------------------------------------------------------------

class TestRegistryClientCache:
    """Tests for TTL-based caching in RegistryClient.search()."""

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_cache_hit_within_ttl(self, mock_request, _mock_session):
        """Second search() with same query within TTL returns cached result — no HTTP call."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agents": SAMPLE_AGENTS}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        client = RegistryClient(api_url=API_URL, cache_ttl=300)

        first = client.search("detect safety signals")
        second = client.search("detect safety signals")

        assert first == second
        assert mock_request.call_count == 1  # only one HTTP call

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_cache_miss_after_ttl(self, mock_request, _mock_session):
        """After TTL expires, search() makes a new HTTP request."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agents": SAMPLE_AGENTS}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        client = RegistryClient(api_url=API_URL, cache_ttl=1)
        client.search("detect safety signals")
        assert mock_request.call_count == 1

        # Manually expire the cache entry
        for entry in client._cache.values():
            entry.cached_at -= 2  # push cached_at back past TTL

        client.search("detect safety signals")
        assert mock_request.call_count == 2

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_cache_invalidation(self, mock_request, _mock_session):
        """invalidate_cache() clears cached entries so next search() hits the API."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agents": SAMPLE_AGENTS}
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        client = RegistryClient(api_url=API_URL, cache_ttl=300)
        client.search("detect safety signals")
        assert mock_request.call_count == 1

        client.invalidate_cache()
        client.search("detect safety signals")
        assert mock_request.call_count == 2


# ---------------------------------------------------------------------------
# Heartbeat tests (Requirement 4)
# ---------------------------------------------------------------------------

class TestRegistryClientHeartbeat:
    """Tests for RegistryClient.heartbeat() — fire-and-forget."""

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_heartbeat_swallows_exceptions(self, mock_request, _mock_session):
        """heartbeat() catches all exceptions and does not propagate them."""
        mock_request.side_effect = Exception("Network error")

        client = RegistryClient(api_url=API_URL)
        # Should not raise
        client.heartbeat("signal_detection-Rb6ez2HHzC")

    @patch("agent_directory.registry_client.boto3.Session", new_callable=_mock_boto3_session)
    @patch("agent_directory.registry_client.requests.request")
    def test_heartbeat_sends_post(self, mock_request, _mock_session):
        """heartbeat() sends POST to /agents/{id}/health."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        client = RegistryClient(api_url=API_URL)
        client.heartbeat("signal_detection-Rb6ez2HHzC")

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == f"{API_URL}/agents/signal_detection-Rb6ez2HHzC/health"
