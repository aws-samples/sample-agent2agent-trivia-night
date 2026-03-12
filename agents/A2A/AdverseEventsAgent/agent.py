"""
Multi-Agent Entrypoint for Adverse Event Signal Detection System

All 4 agents (orchestrator, signal_detection, literature_mining, regulatory_reporting)
share this entrypoint. Routing is based on the A2A protocol 'action' field in the payload:
  - analyze_events       → Signal Detection Agent
  - search_literature    → Literature Mining Agent
  - generate_reports     → Regulatory Reporting Agent
  - list_agents / default→ Orchestrator Agent (full investigation workflow)
"""

import os
import json
import logging
from dataclasses import asdict
from datetime import datetime

import sys
sys.path.append('..')

from models.adverse_event import AdverseEvent
from models.signal import Signal
from config import AgentCoreConfig

# Import agent implementations
from agents.signal_detection_agent import SignalDetectionAgent
from agents.literature_mining_agent import LiteratureMiningAgent
from agents.regulatory_reporting_agent import RegulatoryReportingAgent

# Import Agent Registry (HTTP-based registry client)
from agent_directory.registry_client import RegistryClient
from agents.orchestrator_agent import OrchestratorAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import AgentCore Runtime
try:
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    app = BedrockAgentCoreApp()
    AGENTCORE_AVAILABLE = True
except ImportError:
    logger.warning("bedrock_agentcore.runtime not available")
    app = None
    AGENTCORE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Action handlers for each agent type
# ---------------------------------------------------------------------------

def _parse_signal_from_dict(signal_raw: dict) -> Signal:
    """Parse a Signal dataclass from a raw dict, handling Infinity strings and datetime conversion."""
    # Handle datetime strings
    if isinstance(signal_raw.get("detected_at"), str):
        signal_raw["detected_at"] = datetime.fromisoformat(signal_raw["detected_at"])
    # Handle confidence_interval list → tuple
    if isinstance(signal_raw.get("confidence_interval"), list):
        signal_raw["confidence_interval"] = tuple(signal_raw["confidence_interval"])
    # Handle "Infinity" / "-Infinity" strings → float
    for key in ("prr", "ror", "ic025", "expected_count"):
        val = signal_raw.get(key)
        if isinstance(val, str):
            if val in ("Infinity", "inf"):
                signal_raw[key] = float("inf")
            elif val in ("-Infinity", "-inf"):
                signal_raw[key] = float("-inf")
            else:
                try:
                    signal_raw[key] = float(val)
                except ValueError:
                    pass
    # Handle confidence_interval elements that may be strings
    ci = signal_raw.get("confidence_interval")
    if ci and isinstance(ci, (list, tuple)):
        signal_raw["confidence_interval"] = tuple(
            float(x) if isinstance(x, str) else x for x in ci
        )
    # Filter to valid Signal fields only
    valid_fields = Signal.__dataclass_fields__
    signal_data = {k: v for k, v in signal_raw.items() if k in valid_fields}
    return Signal(**signal_data)

def handle_signal_detection(payload, config):
    """Handle analyze_events action → Signal Detection Agent."""
    agent = SignalDetectionAgent(config=config)

    # Accept events from data.adverse_events (A2A protocol) or top-level adverse_events
    data = payload.get("data", {})
    events_raw = data.get("adverse_events") or payload.get("adverse_events", [])

    if not events_raw:
        return {"success": False, "error": "No adverse events provided"}

    events = []
    for e in events_raw:
        try:
            # Handle datetime strings
            if isinstance(e.get("event_date"), str):
                e["event_date"] = datetime.fromisoformat(e["event_date"])
            events.append(AdverseEvent(**e))
        except Exception as ex:
            logger.warning("Failed to parse adverse event: %s", ex)

    if not events:
        return {"success": False, "error": "No valid adverse events parsed"}

    result = agent.analyze_events(events)
    return {
        "success": True,
        "signals": [asdict(s) for s in result.signals],
        "total_events_analyzed": result.total_events_analyzed,
        "analysis_timestamp": result.analysis_timestamp.isoformat(),
        "errors": result.errors,
    }


def handle_literature_mining(payload, config):
    """Handle search_literature action → Literature Mining Agent."""
    agent = LiteratureMiningAgent(config=config)

    # Accept signal from data.signal (A2A protocol) or top-level signal
    data = payload.get("data", {})
    signal_raw = data.get("signal") or payload.get("signal", {})

    if not signal_raw:
        return {"success": False, "error": "No signal data provided"}

    try:
        signal = _parse_signal_from_dict(signal_raw)
    except Exception as ex:
        return {"success": False, "error": f"Failed to parse signal: {ex}"}

    result = agent.search_literature(signal)
    return {
        "success": True,
        "query": result.query,
        "articles": [asdict(a) for a in result.articles],
        "summary": result.summary,
        "total_results": result.total_results,
        "searched_at": result.searched_at.isoformat(),
    }


def handle_regulatory_reporting(payload, config):
    """Handle generate_reports action → Regulatory Reporting Agent."""
    agent = RegulatoryReportingAgent(config=config)

    # Accept from data.signal_result / data.literature_result (A2A protocol)
    data = payload.get("data", {})
    signal_raw = (
        data.get("signal_result")
        or data.get("signal")
        or payload.get("signal_result")
        or payload.get("signal")
        or {}
    )
    literature_raw = (
        data.get("literature_result")
        or data.get("literature")
        or payload.get("literature_result")
        or payload.get("literature")
    )

    if not signal_raw:
        return {"success": False, "error": "No investigation data provided"}

    try:
        signal = _parse_signal_from_dict(signal_raw)
    except Exception as ex:
        return {"success": False, "error": f"Failed to parse signal: {ex}"}

    # Parse literature if provided (optional)
    literature = None
    if literature_raw and isinstance(literature_raw, dict):
        try:
            from models.literature import LiteratureResults
            literature = LiteratureResults(**literature_raw)
        except Exception:
            logger.warning("Failed to parse literature results, proceeding without")

    reports = agent.generate_reports(signal, literature)
    return {
        "success": True,
        "reports": [asdict(r) for r in reports],
        "count": len(reports),
    }


def handle_orchestrator(payload, config):
    """Handle orchestrator actions (list_agents, full investigation)."""
    registry_client = RegistryClient()
    orchestrator = OrchestratorAgent(config=config, registry_client=registry_client)

    if payload.get("action") == "list_agents":
        agents = orchestrator.list_available_agents()
        return {"success": True, "agents": agents, "count": len(agents)}

    # Full investigation workflow
    data = payload.get("data", {})
    events_raw = data.get("adverse_events") or payload.get("adverse_events", [])
    if not events_raw:
        return {
            "success": False,
            "error": "No adverse events provided",
            "message": "Please provide adverse_events in payload",
        }

    events = []
    for e in events_raw:
        try:
            if isinstance(e.get("event_date"), str):
                e["event_date"] = datetime.fromisoformat(e["event_date"])
            events.append(AdverseEvent(**e))
        except Exception as ex:
            logger.warning("Failed to parse adverse event: %s", ex)

    if not events:
        return {"success": False, "error": "No valid adverse events found"}

    result = orchestrator.initiate_investigation(events)
    return {
        "success": True,
        "investigation_id": result.investigation_id,
        "result": asdict(result),
        "context": {
            "agent_id": "orchestrator",
            "agent_name": "Orchestrator Agent (Dynamic Discovery)",
            "protocol": "a2a",
            "discovery": "a2a_registry_api",
        },
    }


# ---------------------------------------------------------------------------
# Main entrypoint — routes by action field
# ---------------------------------------------------------------------------

ACTION_ROUTER = {
    "analyze_events": handle_signal_detection,
    "search_literature": handle_literature_mining,
    "generate_reports": handle_regulatory_reporting,
    "list_agents": handle_orchestrator,
}


def agent_invocation(payload, context):
    """
    Multi-agent entrypoint. Routes to the correct agent based on the 'action' field.
    """
    logger.info("Agent invoked — payload: %s", json.dumps(payload, default=str)[:500])

    try:
        config = AgentCoreConfig.from_env()
        action = payload.get("action", "")

        handler = ACTION_ROUTER.get(action)
        if handler:
            return handler(payload, config)

        # Default: treat as orchestrator (backward compat)
        return handle_orchestrator(payload, config)

    except Exception as e:
        logger.error("Agent invocation error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# Register entrypoint if AgentCore is available
if AGENTCORE_AVAILABLE and app is not None:
    agent_invocation = app.entrypoint(agent_invocation)


if __name__ == "__main__":
    if AGENTCORE_AVAILABLE and app is not None:
        app.run()
    else:
        logger.error("Cannot run agent: bedrock_agentcore.runtime not available")
