"""Orchestrator Agent for coordinating multi-agent workflow via dynamic discovery."""

import json
import logging
import os
import re
import uuid
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional

import boto3

from models.adverse_event import AdverseEvent
from models.signal import Signal
from models.agent_message import AgentMessage
from models.investigation_result import InvestigationResult
from models.literature import LiteratureResults
from models.regulatory_report import RegulatoryReport

from agent_directory.registry_client import RegistryClient

logger = logging.getLogger(__name__)

# Semantic queries for each workflow step
SIGNAL_DETECTION_QUERY = "detect safety signals in adverse event reports using statistical analysis"
LITERATURE_MINING_QUERY = "search medical literature for drug safety evidence"
REGULATORY_REPORTING_QUERY = "generate regulatory safety reports for FDA and EMA"

# AWS account and region for ARN construction
AWS_ACCOUNT = "730763206378"
AWS_REGION = "us-east-1"


class WorkflowState(Enum):
    """Workflow state machine states."""
    INITIALIZED = "initialized"
    SIGNAL_DETECTION = "signal_detection"
    LITERATURE_MINING = "literature_mining"
    REGULATORY_REPORTING = "regulatory_reporting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class InvestigationState:
    """Internal state tracking for an investigation."""
    investigation_id: str
    workflow_state: WorkflowState
    events: List[AdverseEvent]
    signal: Optional[Signal]
    literature: Optional[LiteratureResults]
    reports: List[RegulatoryReport]
    errors: List[str]
    started_at: datetime
    completed_at: Optional[datetime]
    message_history: List[AgentMessage]


class OrchestratorAgent:
    """
    Agent responsible for coordinating the multi-agent workflow.

    Orchestrates the sequence: Signal Detection → Literature Mining → Regulatory Reporting
    Uses registry-based dynamic discovery and remote invocation via AgentCore Runtime.
    """

    def __init__(self, config=None, registry_client: Optional[RegistryClient] = None):
        """
        Initialize Orchestrator Agent.

        Args:
            config: AgentCore configuration
            registry_client: RegistryClient instance for agent discovery.
                If not provided, a default RegistryClient is created.
        """
        self.config = config
        self.agent_id = "orchestrator_agent"
        self.registry_client = registry_client or RegistryClient()
        self.region = os.environ.get("AWS_REGION", AWS_REGION)
        self.account = AWS_ACCOUNT

        # Track active investigations
        self.active_investigations: Dict[str, InvestigationState] = {}

    def discover_agent(self, query: str) -> Optional[dict]:
        """Semantic search via registry_client.search(). Returns first match or None.

        Args:
            query: Semantic search query describing the desired agent capability.

        Returns:
            First matching agent card dict, or None if no results.
        """
        try:
            results = self.registry_client.search(query)
            if results:
                return results[0]
            return None
        except Exception as e:
            logger.warning("Agent discovery failed for query '%s': %s", query, e)
            return None

    def invoke_remote_agent(self, agent_card: dict, payload: dict) -> dict:
        """Invoke a remote agent via Bedrock AgentCore Runtime.

        Builds the ARN from the agent card's URL field, invokes the agent,
        sends a heartbeat on success, and invalidates cache on failure.

        Args:
            agent_card: Agent card dict with at least a 'url' key.
            payload: Payload dict to send to the agent.

        Returns:
            Parsed response dict on success, or error dict with success=False on failure.
        """
        url = agent_card.get("url", "")
        agent_id = agent_card.get("agent_id", "")
        arn = f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:runtime/{url}"

        try:
            client = boto3.client("bedrock-agentcore", region_name=self.region)
            payload_bytes = json.dumps(payload, default=str).encode("utf-8")
            response = client.invoke_agent_runtime(
                agentRuntimeArn=arn,
                payload=payload_bytes,
                contentType="application/json",
                accept="application/json",
            )

            # Read the streaming response body
            result_text = response["response"].read().decode("utf-8")

            # Send heartbeat on success (fire-and-forget)
            try:
                self.registry_client.heartbeat(agent_id)
            except Exception:
                pass  # heartbeat is fire-and-forget

            # Try to parse as JSON — may be double-encoded (JSON string wrapping Python repr)
            try:
                parsed = json.loads(result_text)
                if isinstance(parsed, dict):
                    return parsed
                # Double-encoded: json.loads returned a string, not a dict
                if isinstance(parsed, str):
                    result_text = parsed
            except (json.JSONDecodeError, TypeError):
                pass

            # AgentCore may return Python repr (single quotes, inf, datetime objects)
            try:
                def _datetime_to_iso(match):
                    """Convert datetime.datetime(...) repr to ISO format string."""
                    try:
                        args = [int(x.strip()) for x in match.group(1).split(",")]
                        dt = datetime(*args)
                        return f'"{dt.isoformat()}"'
                    except Exception:
                        return f'"{datetime.now().isoformat()}"'

                cleaned = result_text
                cleaned = cleaned.replace("'", '"')
                cleaned = cleaned.replace("True", "true").replace("False", "false").replace("None", "null")
                cleaned = re.sub(r'\binf\b', '"Infinity"', cleaned)
                cleaned = re.sub(r'\b-inf\b', '"-Infinity"', cleaned)
                cleaned = re.sub(r'datetime\.datetime\(([^)]+)\)', _datetime_to_iso, cleaned)
                cleaned = re.sub(r'\(([^()]+)\)', r'[\1]', cleaned)
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass

            return {"success": True, "result": result_text}

        except Exception as e:
            logger.error("Failed to invoke agent %s (ARN: %s): %s", agent_id, arn, e)
            self.registry_client.invalidate_cache()
            return {"success": False, "error": str(e)}

    def initiate_investigation(self, adverse_event_data: List[AdverseEvent]) -> InvestigationResult:
        """
        Initiate a new signal investigation workflow.

        Coordinates the complete workflow using dynamic agent discovery:
        1. Signal Detection Agent analyzes events
        2. If signal detected, Literature Mining Agent searches literature
        3. Regulatory Reporting Agent generates reports

        Args:
            adverse_event_data: List of adverse event reports

        Returns:
            InvestigationResult with complete investigation details

        Raises:
            ValueError: If adverse_event_data is empty or invalid
        """
        if not adverse_event_data:
            raise ValueError("adverse_event_data cannot be empty")

        investigation_id = str(uuid.uuid4())
        state = InvestigationState(
            investigation_id=investigation_id,
            workflow_state=WorkflowState.INITIALIZED,
            events=adverse_event_data,
            signal=None,
            literature=None,
            reports=[],
            errors=[],
            started_at=datetime.now(),
            completed_at=None,
            message_history=[],
        )
        self.active_investigations[investigation_id] = state

        try:
            # Step 1: Signal Detection
            state.workflow_state = WorkflowState.SIGNAL_DETECTION
            signal_result = self._run_signal_detection(state)

            if not signal_result:
                state.workflow_state = WorkflowState.COMPLETED
                state.completed_at = datetime.now()
                return self._create_investigation_result(state)

            # Step 2: Literature Mining
            state.workflow_state = WorkflowState.LITERATURE_MINING
            literature_result = self._run_literature_mining(state, signal_result)

            # Step 3: Regulatory Reporting
            state.workflow_state = WorkflowState.REGULATORY_REPORTING
            self._run_regulatory_reporting(state, signal_result, literature_result)

            state.workflow_state = WorkflowState.COMPLETED
            state.completed_at = datetime.now()

        except Exception as e:
            state.workflow_state = WorkflowState.FAILED
            state.errors.append(f"Workflow failed: {str(e)}")
            state.completed_at = datetime.now()

        return self._create_investigation_result(state)

    def list_available_agents(self) -> list[dict]:
        """Return the full list of agents from the registry.

        Passthrough to ``registry_client.list_agents()``.
        """
        return self.registry_client.list_agents()

    # ------------------------------------------------------------------
    # Existing public methods (preserved)
    # ------------------------------------------------------------------

    def handle_agent_response(self, message: AgentMessage) -> None:
        """
        Handle a response message from an agent.

        This method processes agent responses and updates investigation state.
        In a true A2A architecture, this would be the callback for async agent responses.

        Args:
            message: Agent response message
        """
        investigation_id = message.correlation_id

        if investigation_id not in self.active_investigations:
            raise ValueError(f"Unknown investigation: {investigation_id}")

        state = self.active_investigations[investigation_id]
        state.message_history.append(message)

        if message.message_type == "signal_analysis_result":
            self._handle_signal_result(state, message)
        elif message.message_type == "literature_result":
            self._handle_literature_result(state, message)
        elif message.message_type == "report_result":
            self._handle_report_result(state, message)
        elif message.message_type == "error":
            self._handle_error(state, message)

    def get_investigation_status(self, investigation_id: str) -> Dict[str, Any]:
        """
        Get the current status of an investigation.

        Args:
            investigation_id: Investigation ID

        Returns:
            Dictionary with investigation status details

        Raises:
            ValueError: If investigation_id is not found
        """
        if investigation_id not in self.active_investigations:
            raise ValueError(f"Investigation not found: {investigation_id}")

        state = self.active_investigations[investigation_id]

        return {
            "investigation_id": investigation_id,
            "status": state.workflow_state.value,
            "started_at": state.started_at.isoformat(),
            "completed_at": state.completed_at.isoformat() if state.completed_at else None,
            "events_analyzed": len(state.events),
            "signal_detected": state.signal is not None,
            "literature_found": state.literature is not None,
            "reports_generated": len(state.reports),
            "errors": state.errors,
            "message_count": len(state.message_history),
        }

    # ------------------------------------------------------------------
    # Private workflow step methods
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_signal_dict(d: dict) -> dict:
        """Coerce raw signal dict values so they can be passed to Signal(...)."""
        d = dict(d)  # shallow copy
        # Infinity strings → float
        for key in ("prr", "ror", "ic025", "expected_count"):
            val = d.get(key)
            if isinstance(val, str):
                if val in ("Infinity", "inf"):
                    d[key] = float("inf")
                elif val in ("-Infinity", "-inf"):
                    d[key] = float("-inf")
                else:
                    try:
                        d[key] = float(val)
                    except ValueError:
                        pass
        # datetime string → datetime
        if isinstance(d.get("detected_at"), str):
            d["detected_at"] = datetime.fromisoformat(d["detected_at"])
        # list → tuple for confidence_interval
        ci = d.get("confidence_interval")
        if isinstance(ci, list):
            d["confidence_interval"] = tuple(
                float(x) if isinstance(x, str) else x for x in ci
            )
        return d

    def _run_signal_detection(self, state: InvestigationState) -> Optional[dict]:
        """Run signal detection via dynamic discovery and remote invocation.

        Returns the invocation result dict if signals were found, or None.
        """
        try:
            agent_card = self.discover_agent(SIGNAL_DETECTION_QUERY)
            if not agent_card:
                state.errors.append("No signal detection agent found in registry")
                return None

            payload = {
                "protocol": "a2a",
                "sender": "orchestrator",
                "message_id": f"msg_{uuid.uuid4().hex[:12]}",
                "action": "analyze_events",
                "data": {"adverse_events": [e.__dict__ for e in state.events]},
            }

            result = self.invoke_remote_agent(agent_card, payload)

            if result.get("success") is False:
                state.errors.append(f"Signal detection failed: {result.get('error', 'unknown')}")
                return None

            # Store signal info in state if present
            signal_data = result.get("signal") or result.get("signals")
            if signal_data:
                # signals may be a list — take the first (strongest) signal
                if isinstance(signal_data, list) and signal_data:
                    signal_data = signal_data[0]
                if isinstance(signal_data, dict):
                    try:
                        coerced = self._coerce_signal_dict(signal_data)
                        state.signal = Signal(**{
                            k: v for k, v in coerced.items()
                            if k in Signal.__dataclass_fields__
                        })
                    except Exception as e:
                        logger.warning("Failed to parse Signal from response: %s", e)

            return result

        except Exception as e:
            state.errors.append(f"Signal detection failed: {str(e)}")
            return None

    def _run_literature_mining(
        self, state: InvestigationState, signal_result: dict
    ) -> Optional[dict]:
        """Run literature mining via dynamic discovery and remote invocation."""
        try:
            agent_card = self.discover_agent(LITERATURE_MINING_QUERY)
            if not agent_card:
                state.errors.append("No literature mining agent found in registry")
                return None

            # Extract the first signal dict from the signal detection response
            signals = signal_result.get("signals", [])
            signal_data = signals[0] if signals else signal_result.get("signal", {})

            payload = {
                "protocol": "a2a",
                "sender": "orchestrator",
                "message_id": f"msg_{uuid.uuid4().hex[:12]}",
                "action": "search_literature",
                "data": {"signal": signal_data},
            }

            result = self.invoke_remote_agent(agent_card, payload)

            if result.get("success") is False:
                state.errors.append(f"Literature mining failed: {result.get('error', 'unknown')}")
                return None

            return result

        except Exception as e:
            state.errors.append(f"Literature mining failed: {str(e)}")
            return None

    def _run_regulatory_reporting(
        self,
        state: InvestigationState,
        signal_result: dict,
        literature_result: Optional[dict],
    ) -> Optional[dict]:
        """Run regulatory reporting via dynamic discovery and remote invocation."""
        try:
            agent_card = self.discover_agent(REGULATORY_REPORTING_QUERY)
            if not agent_card:
                state.errors.append("No regulatory reporting agent found in registry")
                return None

            # Extract the first signal dict from the signal detection response
            signals = signal_result.get("signals", [])
            signal_data = signals[0] if signals else signal_result.get("signal", {})

            payload = {
                "protocol": "a2a",
                "sender": "orchestrator",
                "message_id": f"msg_{uuid.uuid4().hex[:12]}",
                "action": "generate_reports",
                "data": {
                    "signal_result": signal_data,
                    "literature_result": literature_result,
                },
            }

            result = self.invoke_remote_agent(agent_card, payload)

            if result.get("success") is False:
                state.errors.append(
                    f"Regulatory reporting failed: {result.get('error', 'unknown')}"
                )
                return None

            return result

        except Exception as e:
            state.errors.append(f"Regulatory reporting failed: {str(e)}")
            return None

    # ------------------------------------------------------------------
    # Private message handlers (preserved)
    # ------------------------------------------------------------------

    def _handle_signal_result(self, state: InvestigationState, message: AgentMessage) -> None:
        """Handle signal detection result message."""
        signal_data = message.payload.get("signal")
        if signal_data:
            state.signal = Signal(**signal_data)

    def _handle_literature_result(self, state: InvestigationState, message: AgentMessage) -> None:
        """Handle literature mining result message."""
        literature_data = message.payload.get("literature")
        if literature_data:
            state.literature = LiteratureResults(**literature_data)

    def _handle_report_result(self, state: InvestigationState, message: AgentMessage) -> None:
        """Handle regulatory reporting result message."""
        reports_data = message.payload.get("reports", [])
        state.reports = [RegulatoryReport(**r) for r in reports_data]

    def _handle_error(self, state: InvestigationState, message: AgentMessage) -> None:
        """Handle error message from agent."""
        error_msg = message.payload.get("error", "Unknown error")
        state.errors.append(f"{message.sender_agent_id}: {error_msg}")

    def _create_investigation_result(self, state: InvestigationState) -> InvestigationResult:
        """Create InvestigationResult from investigation state."""
        if state.workflow_state == WorkflowState.COMPLETED:
            status = "completed"
        elif state.workflow_state == WorkflowState.FAILED:
            status = "failed"
        else:
            status = "in_progress"

        return InvestigationResult(
            investigation_id=state.investigation_id,
            status=status,
            signal=state.signal,
            literature=state.literature,
            reports=state.reports,
            errors=state.errors,
            started_at=state.started_at,
            completed_at=state.completed_at,
        )
