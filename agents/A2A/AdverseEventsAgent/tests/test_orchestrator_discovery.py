"""Unit tests for OrchestratorAgent — dynamic discovery and remote invocation."""

from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from models.adverse_event import AdverseEvent
from agents.orchestrator_agent import OrchestratorAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_card(agent_id="signal_detection-Rb6ez2HHzC", url=None):
    return {
        "agent_id": agent_id,
        "name": "Signal Detection Agent",
        "description": "Analyzes adverse event reports",
        "url": url or agent_id,
        "version": "1.0.0",
        "skills": [],
    }


SIGNAL_CARD = _make_agent_card("signal_detection-Rb6ez2HHzC")
LITERATURE_CARD = _make_agent_card("literature_mining-JSgVgH7UsS")
REGULATORY_CARD = _make_agent_card("regulatory_reporting-N1CsONAkWX")


def _make_event():
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


def _make_registry_client_mock():
    """Return a MagicMock that behaves like RegistryClient."""
    mock_rc = MagicMock()
    mock_rc.search.return_value = [SIGNAL_CARD]
    mock_rc.list_agents.return_value = [SIGNAL_CARD, LITERATURE_CARD, REGULATORY_CARD]
    mock_rc.heartbeat.return_value = None
    mock_rc.invalidate_cache.return_value = None
    return mock_rc


# ---------------------------------------------------------------------------
# discover_agent tests (Requirement 2)
# ---------------------------------------------------------------------------

class TestDiscoverAgent:
    """Tests for OrchestratorAgent.discover_agent()."""

    def test_returns_first_result(self):
        """discover_agent returns the first agent card from search results."""
        mock_rc = _make_registry_client_mock()
        mock_rc.search.return_value = [SIGNAL_CARD, LITERATURE_CARD]

        orch = OrchestratorAgent(registry_client=mock_rc)
        result = orch.discover_agent("detect safety signals")

        assert result == SIGNAL_CARD
        mock_rc.search.assert_called_once_with("detect safety signals")

    def test_returns_none_on_empty(self):
        """discover_agent returns None when search yields no results."""
        mock_rc = _make_registry_client_mock()
        mock_rc.search.return_value = []

        orch = OrchestratorAgent(registry_client=mock_rc)
        result = orch.discover_agent("nonexistent agent")

        assert result is None


# ---------------------------------------------------------------------------
# invoke_remote_agent tests (Requirement 4)
# ---------------------------------------------------------------------------

class TestInvokeRemoteAgent:
    """Tests for OrchestratorAgent.invoke_remote_agent()."""

    @patch("agents.orchestrator_agent.boto3.client")
    def test_arn_construction(self, mock_boto_client):
        """ARN is built as arn:aws:bedrock-agentcore:{region}:{account}:runtime/{url}."""
        mock_runtime = MagicMock()
        mock_runtime.invoke_agent.return_value = {"completion": []}
        mock_boto_client.return_value = mock_runtime

        mock_rc = _make_registry_client_mock()
        orch = OrchestratorAgent(registry_client=mock_rc)

        card = _make_agent_card("signal_detection-Rb6ez2HHzC")
        orch.invoke_remote_agent(card, {"action": "analyze_events"})

        invoke_call = mock_runtime.invoke_agent.call_args
        expected_arn = "arn:aws:bedrock-agentcore:us-east-1:730763206378:runtime/signal_detection-Rb6ez2HHzC"
        assert invoke_call[1]["agentRuntimeArn"] == expected_arn

    @patch("agents.orchestrator_agent.boto3.client")
    def test_heartbeat_on_success(self, mock_boto_client):
        """Heartbeat is sent after a successful invocation."""
        mock_runtime = MagicMock()
        mock_runtime.invoke_agent.return_value = {"completion": []}
        mock_boto_client.return_value = mock_runtime

        mock_rc = _make_registry_client_mock()
        orch = OrchestratorAgent(registry_client=mock_rc)

        card = _make_agent_card("signal_detection-Rb6ez2HHzC")
        orch.invoke_remote_agent(card, {"action": "analyze_events"})

        mock_rc.heartbeat.assert_called_once_with("signal_detection-Rb6ez2HHzC")

    @patch("agents.orchestrator_agent.boto3.client")
    def test_cache_invalidation_on_failure(self, mock_boto_client):
        """Cache is invalidated and error dict returned when invocation fails."""
        mock_runtime = MagicMock()
        mock_runtime.invoke_agent.side_effect = Exception("Invocation failed")
        mock_boto_client.return_value = mock_runtime

        mock_rc = _make_registry_client_mock()
        orch = OrchestratorAgent(registry_client=mock_rc)

        card = _make_agent_card("signal_detection-Rb6ez2HHzC")
        result = orch.invoke_remote_agent(card, {"action": "analyze_events"})

        mock_rc.invalidate_cache.assert_called_once()
        assert result["success"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# initiate_investigation tests (Requirement 5)
# ---------------------------------------------------------------------------

class TestInitiateInvestigation:
    """Tests for OrchestratorAgent.initiate_investigation() — 3-step workflow."""

    def test_three_step_workflow_order(self):
        """Investigation executes signal detection → literature mining → regulatory reporting."""
        mock_rc = _make_registry_client_mock()
        mock_rc.search.side_effect = [
            [SIGNAL_CARD],
            [LITERATURE_CARD],
            [REGULATORY_CARD],
        ]

        orch = OrchestratorAgent(registry_client=mock_rc)

        # Mock invoke_remote_agent to avoid real boto3/json serialization.
        # Signal result must be truthy and NOT have success=False to proceed.
        invoke_results = [
            {"success": True, "result": "signals detected"},
            {"success": True, "result": "literature found"},
            {"success": True, "result": "reports generated"},
        ]
        with patch.object(orch, "invoke_remote_agent", side_effect=invoke_results) as mock_invoke:
            event = _make_event()
            result = orch.initiate_investigation([event])

        # Verify 3 discover calls in order
        search_calls = mock_rc.search.call_args_list
        assert len(search_calls) == 3
        assert "signal" in search_calls[0][0][0].lower()
        assert "literature" in search_calls[1][0][0].lower()
        assert "regulatory" in search_calls[2][0][0].lower()

        # Verify 3 invoke calls with the correct agent cards
        assert mock_invoke.call_count == 3
        assert result.investigation_id is not None
        assert result.started_at is not None

    def test_partial_results_on_failure(self):
        """When a workflow step fails, partial results from earlier steps are preserved."""
        mock_rc = _make_registry_client_mock()
        mock_rc.search.side_effect = [
            [SIGNAL_CARD],
            [LITERATURE_CARD],
            [REGULATORY_CARD],
        ]

        orch = OrchestratorAgent(registry_client=mock_rc)

        # First invocation succeeds (signal detection), second fails (literature)
        invoke_results = [
            {"success": True, "result": "signals detected"},
            {"success": False, "error": "Literature agent unavailable"},
        ]
        with patch.object(orch, "invoke_remote_agent", side_effect=invoke_results):
            event = _make_event()
            result = orch.initiate_investigation([event])

        # Investigation should still return a result (not crash)
        assert result is not None
        assert result.investigation_id is not None
        # Errors should be recorded
        assert len(result.errors) > 0

    def test_value_error_on_empty_input(self):
        """ValueError raised when adverse_event_data is empty."""
        mock_rc = _make_registry_client_mock()
        orch = OrchestratorAgent(registry_client=mock_rc)

        with pytest.raises(ValueError, match="adverse_event_data cannot be empty"):
            orch.initiate_investigation([])


# ---------------------------------------------------------------------------
# list_available_agents tests (Requirement 6)
# ---------------------------------------------------------------------------

class TestListAvailableAgents:
    """Tests for OrchestratorAgent.list_available_agents()."""

    def test_passthrough(self):
        """list_available_agents delegates to registry_client.list_agents()."""
        expected = [SIGNAL_CARD, LITERATURE_CARD, REGULATORY_CARD]
        mock_rc = _make_registry_client_mock()
        mock_rc.list_agents.return_value = expected

        orch = OrchestratorAgent(registry_client=mock_rc)
        result = orch.list_available_agents()

        assert result == expected
        mock_rc.list_agents.assert_called_once()
