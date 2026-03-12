"""HTTP client for the A2A Agent Registry API with SigV4 auth and TTL caching.

Talks to the deployed A2A Agent Registry REST API using IAM SigV4
authentication. Search results are cached in-memory with a configurable TTL
to avoid redundant API calls within a single workflow execution.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import boto3
import requests
from requests_aws4auth import AWS4Auth

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """In-memory cache entry with TTL."""

    result: list[dict]
    cached_at: float
    ttl: int


class RegistryClient:
    """Talks to the A2A Agent Registry API with IAM SigV4 auth."""

    def __init__(
        self,
        api_url: str | None = None,
        region: str | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        """Reads config from params or env vars.

        Args:
            api_url: Base URL for the registry API. Falls back to
                ``A2A_REGISTRY_API_URL`` env var.
            region: AWS region for SigV4 signing. Falls back to
                ``AWS_REGION`` env var, then defaults to ``us-east-1``.
            cache_ttl: Cache time-to-live in seconds. Falls back to
                ``AGENT_DISCOVERY_CACHE_TTL`` env var, then defaults to 300.

        Raises:
            ValueError: If no API URL is available from param or env var.
        """
        self.api_url = api_url or os.environ.get("A2A_REGISTRY_API_URL")
        if not self.api_url:
            raise ValueError(
                "api_url must be provided or A2A_REGISTRY_API_URL environment variable must be set"
            )
        # Strip trailing slash for consistent URL joining
        self.api_url = self.api_url.rstrip("/")

        self.region = region or os.environ.get("AWS_REGION", "us-east-1")

        if cache_ttl is not None:
            self.cache_ttl = cache_ttl
        else:
            env_ttl = os.environ.get("AGENT_DISCOVERY_CACHE_TTL")
            self.cache_ttl = int(env_ttl) if env_ttl else 300

        self._cache: dict[str, CacheEntry] = {}

        # Build SigV4 auth from current boto3 credentials
        session = boto3.Session(region_name=self.region)
        credentials = session.get_credentials().get_frozen_credentials()
        self._auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            self.region,
            "execute-api",
            session_token=credentials.token,
        )


    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    def _sign_request(
        self, method: str, url: str, **kwargs
    ) -> requests.Response:
        """Sign and send an HTTP request with SigV4."""
        return requests.request(method, url, auth=self._auth, timeout=10, **kwargs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Semantic search for agents.

        Sends a SigV4-signed GET to ``/agents/search`` with *query* and
        *top_k* parameters.  Results are cached by ``{query}:{top_k}``
        with the configured TTL.

        Returns an empty list on any HTTP or network error.
        """
        cache_key = f"{query}:{top_k}"

        # Check cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if time.time() - entry.cached_at < entry.ttl:
                return entry.result
            del self._cache[cache_key]

        # HTTP call with SigV4
        try:
            resp = self._sign_request(
                "GET",
                f"{self.api_url}/agents/search",
                params={"query": query, "top_k": top_k},
            )
            resp.raise_for_status()
            body = resp.json()
            results = body.get("results", body.get("agents", []))
        except Exception as e:
            logger.warning("Registry search failed: %s", e)
            return []

        # Cache the results
        self._cache[cache_key] = CacheEntry(
            result=results, cached_at=time.time(), ttl=self.cache_ttl
        )
        return results

    def get_agent(self, agent_id: str) -> dict | None:
        """Fetch a single agent by ID.

        Returns ``None`` when the agent is not found or on error.
        """
        try:
            resp = self._sign_request("GET", f"{self.api_url}/agents/{agent_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Failed to get agent %s: %s", agent_id, e)
            return None

    def list_agents(self) -> list[dict]:
        """List all registered agents via ``GET /agents``."""
        try:
            resp = self._sign_request("GET", f"{self.api_url}/agents")
            resp.raise_for_status()
            return resp.json().get("agents", [])
        except Exception as e:
            logger.warning("Failed to list agents: %s", e)
            return []

    def heartbeat(self, agent_id: str) -> None:
        """Send a heartbeat for *agent_id*.

        Fire-and-forget: catches **all** exceptions and only logs a
        warning so that heartbeat failures never block the workflow.
        """
        try:
            resp = self._sign_request(
                "POST", f"{self.api_url}/agents/{agent_id}/health"
            )
            resp.raise_for_status()
            logger.debug("Heartbeat sent for agent: %s", agent_id)
        except Exception:
            logger.warning(
                "Failed to send heartbeat for agent %s", agent_id, exc_info=True
            )

    def invalidate_cache(self, query: str | None = None) -> None:
        """Invalidate cached search results.

        Args:
            query: If provided, remove only cache entries whose key
                starts with this query string.  If ``None``, clear the
                entire cache.
        """
        if query is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k in self._cache if k.startswith(f"{query}:")]
            for key in keys_to_remove:
                del self._cache[key]
