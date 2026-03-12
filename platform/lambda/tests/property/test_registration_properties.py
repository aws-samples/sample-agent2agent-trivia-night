"""
Property-based tests for the registration scripts.

Tests cover:
- Property 18: Deploy-and-Register Wrapper Extracts Endpoint URL
- Property 19: Registration Script Argument Parsing and Payload Construction
- Property 20: Failed Registration Exits with Error

The scripts under test live in ``Agent2Agent-Trivia-Night-Examples/scripts/``.
We add that directory to ``sys.path`` so we can import functions directly.

Uses ``hypothesis`` with a minimum of 100 examples per property.
"""

import importlib
import json
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Import helpers – add the scripts directory to sys.path
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts")
)

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _import_script(module_name: str, file_name: str) -> ModuleType:
    """Import a script module by file name, handling hyphens in names."""
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(_SCRIPTS_DIR, file_name)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Import the two scripts as modules
deploy_and_register = _import_script("deploy_and_register", "deploy_and_register.py")
register_agent = _import_script("register_agent_mod", "register_agent.py")


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Non-empty printable text for names / descriptions
_non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=120,
).filter(lambda s: s.strip())

# URL-like strings
_url_strategy = st.from_regex(
    r"https://[a-z0-9\-]+\.example\.com/[a-z0-9/\-]+", fullmatch=True
)

# Skill name strategy
_skill_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# List of skills (0-5 items)
_skills_list = st.lists(_skill_name, min_size=0, max_size=5)


# ===================================================================
# Property 18: Deploy-and-Register Wrapper Extracts Endpoint URL
# Feature: lss-workshop-platform, Property 18: Deploy-and-Register
#   Wrapper Extracts Endpoint URL
# **Validates: Requirements 12.2, 12.3**
# ===================================================================


class TestDeployAndRegisterExtractsEndpointURL:
    """Property 18: For any valid agentcore status JSON containing an
    endpoint with status READY, extract_endpoint_url correctly returns
    the endpoint URL."""

    @given(
        url=_url_strategy,
        extra_endpoints=st.lists(
            st.fixed_dictionaries({
                "status": st.sampled_from(["CREATING", "UPDATING", "FAILED"]),
                "url": _url_strategy,
            }),
            min_size=0,
            max_size=3,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_extracts_url_from_endpoints_list(self, url: str, extra_endpoints: list):
        """READY endpoint URL is extracted from the endpoints list shape."""
        ready_entry = {"status": "READY", "url": url}
        # Place the READY entry at a random position among non-ready entries
        all_endpoints = extra_endpoints + [ready_entry]

        status_json = {"endpoints": all_endpoints}
        result = deploy_and_register.extract_endpoint_url(status_json)
        assert result == url

    @given(url=_url_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_extracts_url_from_flat_status(self, url: str):
        """READY endpoint URL is extracted from the flat status shape."""
        status_json = {"status": "READY", "url": url}
        result = deploy_and_register.extract_endpoint_url(status_json)
        assert result == url

    @given(url=_url_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_extracts_endpoint_url_key(self, url: str):
        """READY endpoint URL is extracted when key is 'endpoint_url'."""
        status_json = {
            "endpoints": [{"status": "READY", "endpoint_url": url}]
        }
        result = deploy_and_register.extract_endpoint_url(status_json)
        assert result == url

    @given(
        non_ready_endpoints=st.lists(
            st.fixed_dictionaries({
                "status": st.sampled_from(["CREATING", "UPDATING", "FAILED"]),
                "url": _url_strategy,
            }),
            min_size=0,
            max_size=4,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_returns_none_when_no_ready_endpoint(self, non_ready_endpoints: list):
        """Returns None when no endpoint has READY status."""
        status_json = {"endpoints": non_ready_endpoints}
        result = deploy_and_register.extract_endpoint_url(status_json)
        assert result is None



# ===================================================================
# Property 19: Registration Script Argument Parsing and Payload
#   Construction
# Feature: lss-workshop-platform, Property 19: Registration Script
#   Argument Parsing and Payload Construction
# **Validates: Requirements 12.10, 12.11**
# ===================================================================


class TestRegistrationArgumentParsingAndPayload:
    """Property 19: For any valid combination of CLI arguments, the
    standalone registration script constructs an Agent_Card JSON payload
    containing all provided fields with their exact values."""

    @given(
        name=_non_empty_text,
        description=_non_empty_text,
        url=_url_strategy,
        skills=_skills_list,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_build_agent_card_contains_all_fields(
        self, name: str, description: str, url: str, skills: list
    ):
        """build_agent_card includes name, description, url, and skills."""
        card = register_agent.build_agent_card(name, description, url, skills)

        assert card["name"] == name
        assert card["description"] == description
        assert card["url"] == url

        if skills:
            assert "skills" in card
            assert len(card["skills"]) == len(skills)
            for i, skill_name in enumerate(skills):
                assert card["skills"][i]["id"] == skill_name
                assert card["skills"][i]["name"] == skill_name
        else:
            # When no skills provided, the key should be absent
            assert "skills" not in card

    @given(
        name=_non_empty_text,
        description=_non_empty_text,
        url=_url_strategy,
        skills=_skills_list,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_deploy_wrapper_build_agent_card_matches(
        self, name: str, description: str, url: str, skills: list
    ):
        """deploy_and_register.build_agent_card produces the same payload
        structure as register_agent.build_agent_card."""
        card_deploy = deploy_and_register.build_agent_card(name, description, url, skills)
        card_standalone = register_agent.build_agent_card(name, description, url, skills)

        assert card_deploy == card_standalone

    @given(
        name=_non_empty_text,
        description=_non_empty_text,
        url=_url_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_payload_is_json_serializable(
        self, name: str, description: str, url: str
    ):
        """The constructed agent card is always JSON-serializable."""
        card = register_agent.build_agent_card(name, description, url, [])
        serialized = json.dumps(card)
        deserialized = json.loads(serialized)
        assert deserialized["name"] == name
        assert deserialized["description"] == description
        assert deserialized["url"] == url



# ===================================================================
# Property 20: Failed Registration Exits with Error
# Feature: lss-workshop-platform, Property 20: Failed Registration
#   Exits with Error
# **Validates: Requirements 12.7, 12.8**
# ===================================================================


class TestFailedRegistrationExitsWithError:
    """Property 20: For any API error response (non-2xx status), the
    registration scripts print the error message and HTTP status code
    to stderr and exit with a non-zero exit code."""

    @given(
        status_code=st.integers(min_value=400, max_value=599),
        error_body=_non_empty_text,
        api_url=_url_strategy,
        region=st.just("us-east-1"),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_register_agent_standalone_exits_on_error(
        self, status_code: int, error_body: str, api_url: str, region: str
    ):
        """register_agent.register_agent exits with SystemExit on HTTP errors."""
        agent_card = {"name": "test", "description": "test", "url": "https://example.com"}

        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = error_body

        with patch.object(register_agent, "requests") as mock_requests, \
             patch.object(register_agent, "boto3") as mock_boto3:
            # Set up boto3 credentials mock
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_creds.access_key = "AKIAIOSFODNN7EXAMPLE"
            mock_creds.secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            mock_creds.token = "test-token"
            mock_session.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
            mock_boto3.Session.return_value = mock_session

            mock_requests.post.return_value = mock_response

            with pytest.raises(SystemExit) as exc_info:
                register_agent.register_agent(api_url, agent_card, region)

            assert exc_info.value.code == 1

    @given(
        status_code=st.integers(min_value=400, max_value=599),
        error_body=_non_empty_text,
        api_url=_url_strategy,
        region=st.just("us-east-1"),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_deploy_wrapper_register_exits_on_error(
        self, status_code: int, error_body: str, api_url: str, region: str
    ):
        """deploy_and_register.register_agent exits with SystemExit on HTTP errors."""
        agent_card = {"name": "test", "description": "test", "url": "https://example.com"}

        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = error_body

        with patch.object(deploy_and_register, "requests") as mock_requests, \
             patch.object(deploy_and_register, "boto3") as mock_boto3:
            # Set up boto3 credentials mock
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_creds.access_key = "AKIAIOSFODNN7EXAMPLE"
            mock_creds.secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            mock_creds.token = "test-token"
            mock_session.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
            mock_boto3.Session.return_value = mock_session

            mock_requests.post.return_value = mock_response

            with pytest.raises(SystemExit) as exc_info:
                deploy_and_register.register_agent(api_url, agent_card, region)

            assert exc_info.value.code == 1

    @given(
        status_code=st.integers(min_value=400, max_value=599),
        error_body=_non_empty_text,
        api_url=_url_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_error_message_written_to_stderr(
        self, status_code: int, error_body: str, api_url: str
    ):
        """Error output includes the HTTP status code."""
        agent_card = {"name": "test", "description": "test", "url": "https://example.com"}

        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = error_body

        with patch.object(register_agent, "requests") as mock_requests, \
             patch.object(register_agent, "boto3") as mock_boto3:
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_creds.access_key = "AKIAIOSFODNN7EXAMPLE"
            mock_creds.secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            mock_creds.token = "test-token"
            mock_session.get_credentials.return_value.get_frozen_credentials.return_value = mock_creds
            mock_boto3.Session.return_value = mock_session

            mock_requests.post.return_value = mock_response

            import io
            from contextlib import redirect_stderr

            stderr_capture = io.StringIO()
            with redirect_stderr(stderr_capture):
                with pytest.raises(SystemExit):
                    register_agent.register_agent(api_url, agent_card, "us-east-1")

            stderr_output = stderr_capture.getvalue()
            assert str(status_code) in stderr_output
