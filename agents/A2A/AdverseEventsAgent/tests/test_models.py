"""Basic tests for data models."""

import pytest
from datetime import datetime
from models.adverse_event import AdverseEvent
from models.signal import Signal
from models.literature import Article, LiteratureResults
from models.regulatory_report import RegulatoryReport
from models.agent_message import AgentMessage
from models.investigation_result import InvestigationResult


class TestAdverseEvent:
    """Tests for AdverseEvent model."""
    
    def test_create_valid_adverse_event(self):
        """Test creating a valid adverse event."""
        event = AdverseEvent(
            event_id="AE001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            medra_code="12345678",
            patient_age=65,
            patient_sex="M",
            event_date=datetime.now(),
            outcome="hospitalization",
            reporter_type="physician"
        )
        assert event.event_id == "AE001"
        assert event.drug_name == "DrugX"
    
    def test_adverse_event_requires_event_id(self):
        """Test that event_id is required."""
        with pytest.raises(ValueError, match="event_id is required"):
            AdverseEvent(
                event_id="",
                drug_name="DrugX",
                adverse_event_term="Cardiac Arrhythmia",
                medra_code="12345678",
                patient_age=65,
                patient_sex="M",
                event_date=datetime.now(),
                outcome="hospitalization",
                reporter_type="physician"
            )


class TestSignal:
    """Tests for Signal model."""
    
    def test_create_valid_signal(self):
        """Test creating a valid signal."""
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=50,
            expected_count=10.5,
            prr=4.76,
            ror=5.12,
            ic025=1.5,
            confidence_interval=(1.5, 2.8),
            detected_at=datetime.now(),
            severity="high"
        )
        assert signal.signal_id == "SIG001"
        assert signal.is_flagged() is True
    
    def test_signal_flagging_logic(self):
        """Test signal flagging based on IC025."""
        signal_flagged = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Event",
            event_count=10,
            expected_count=5.0,
            prr=2.0,
            ror=2.0,
            ic025=0.5,
            confidence_interval=(0.5, 1.5),
            detected_at=datetime.now(),
            severity="medium"
        )
        assert signal_flagged.is_flagged() is True
        
        signal_not_flagged = Signal(
            signal_id="SIG002",
            drug_name="DrugY",
            adverse_event_term="Event",
            event_count=10,
            expected_count=5.0,
            prr=2.0,
            ror=2.0,
            ic025=-0.5,
            confidence_interval=(-0.5, 0.5),
            detected_at=datetime.now(),
            severity="low"
        )
        assert signal_not_flagged.is_flagged() is False


class TestAgentMessage:
    """Tests for AgentMessage model."""
    
    def test_create_valid_message(self):
        """Test creating a valid agent message."""
        message = AgentMessage(
            message_id="MSG001",
            message_type="signal_detected",
            sender_agent_id="signal_detection_agent",
            recipient_agent_id="orchestrator",
            timestamp=datetime.now(),
            payload={"signal_id": "SIG001"},
            correlation_id="INV001"
        )
        assert message.message_id == "MSG001"
        assert message.message_type == "signal_detected"
    
    def test_message_type_validation(self):
        """Test that invalid message types are rejected."""
        with pytest.raises(ValueError, match="message_type must be one of"):
            AgentMessage(
                message_id="MSG001",
                message_type="invalid_type",
                sender_agent_id="agent1",
                recipient_agent_id="agent2",
                timestamp=datetime.now(),
                payload={},
                correlation_id="INV001"
            )


class TestInvestigationResult:
    """Tests for InvestigationResult model."""
    
    def test_create_in_progress_investigation(self):
        """Test creating an in-progress investigation."""
        result = InvestigationResult(
            investigation_id="INV001",
            status="in_progress",
            signal=None,
            literature=None,
            reports=[],
            errors=[],
            started_at=datetime.now(),
            completed_at=None
        )
        assert result.investigation_id == "INV001"
        assert result.status == "in_progress"
    
    def test_completed_investigation_allows_no_signal(self):
        """Test that completed investigation can have no signal (when none detected)."""
        result = InvestigationResult(
            investigation_id="INV001",
            status="completed",
            signal=None,  # No signal detected
            literature=None,
            reports=[],
            errors=[],
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        
        assert result.investigation_id == "INV001"
        assert result.status == "completed"
        assert result.signal is None

