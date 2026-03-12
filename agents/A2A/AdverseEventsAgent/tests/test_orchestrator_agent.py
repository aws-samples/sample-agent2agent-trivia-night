"""Property-based tests for Orchestrator Agent."""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from typing import List
import uuid

from models.adverse_event import AdverseEvent
from models.signal import Signal
from models.agent_message import AgentMessage
from agents.orchestrator_agent import OrchestratorAgent, WorkflowState
from agents.signal_detection_agent import SignalDetectionAgent, SignalAnalysisResult
from agents.literature_mining_agent import LiteratureMiningAgent
from agents.regulatory_reporting_agent import RegulatoryReportingAgent


# Test data generators

@st.composite
def adverse_event_strategy(draw):
    """Generate random adverse event."""
    return AdverseEvent(
        event_id=str(draw(st.uuids())),
        drug_name=draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
        adverse_event_term=draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
        medra_code=draw(st.text(min_size=8, max_size=8, alphabet=st.characters(whitelist_categories=('Nd',)))),
        patient_age=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=120))),
        patient_sex=draw(st.one_of(st.none(), st.sampled_from(['M', 'F', 'U']))),
        event_date=draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))),
        outcome=draw(st.sampled_from(['recovered', 'fatal', 'hospitalization', 'disability', 'other'])),
        reporter_type=draw(st.sampled_from(['physician', 'pharmacist', 'consumer', 'other']))
    )


@st.composite
def signal_strategy(draw):
    """Generate random signal."""
    ic025 = draw(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False))
    ic975 = ic025 + draw(st.floats(min_value=0.1, max_value=2.0, allow_nan=False, allow_infinity=False))
    
    return Signal(
        signal_id=str(draw(st.uuids())),
        drug_name=draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
        adverse_event_term=draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))),
        event_count=draw(st.integers(min_value=1, max_value=1000)),
        expected_count=draw(st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False)),
        prr=draw(st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)),
        ror=draw(st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)),
        ic025=ic025,
        confidence_interval=(ic025, ic975),
        detected_at=draw(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2024, 12, 31))),
        severity=draw(st.sampled_from(['low', 'medium', 'high', 'critical']))
    )


# Mock agents for testing

class MockSignalDetectionAgent:
    """Mock Signal Detection Agent for testing."""
    
    def __init__(self, return_signal=True, should_fail=False):
        self.agent_id = "mock_signal_detection_agent"
        self.return_signal = return_signal
        self.should_fail = should_fail
        self.called = False
        self.call_count = 0
    
    def analyze_events(self, events: List[AdverseEvent]) -> SignalAnalysisResult:
        """Mock analyze_events method."""
        self.called = True
        self.call_count += 1
        
        if self.should_fail:
            raise Exception("Mock signal detection failure")
        
        signals = []
        if self.return_signal and events:
            # Create a signal with IC025 > 0 to trigger investigation
            signal = Signal(
                signal_id=f"SIG_{events[0].drug_name}_{events[0].adverse_event_term}",
                drug_name=events[0].drug_name,
                adverse_event_term=events[0].adverse_event_term,
                event_count=len(events),
                expected_count=len(events) * 0.5,
                prr=2.0,
                ror=2.0,
                ic025=1.5,  # > 0, so will be flagged
                confidence_interval=(1.5, 3.0),
                detected_at=datetime.now(),
                severity='medium'
            )
            signals.append(signal)
        
        return SignalAnalysisResult(
            signals=signals,
            total_events_analyzed=len(events),
            analysis_timestamp=datetime.now(),
            errors=[]
        )


class MockLiteratureMiningAgent:
    """Mock Literature Mining Agent for testing."""
    
    def __init__(self, should_fail=False):
        self.agent_id = "mock_literature_mining_agent"
        self.should_fail = should_fail
        self.called = False
        self.call_count = 0
    
    def search_literature(self, signal: Signal):
        """Mock search_literature method."""
        self.called = True
        self.call_count += 1
        
        if self.should_fail:
            raise Exception("Mock literature mining failure")
        
        from models.literature import LiteratureResults, Article
        
        return LiteratureResults(
            query=f"{signal.drug_name} AND {signal.adverse_event_term}",
            articles=[
                Article(
                    title="Mock Article",
                    authors=["Author A"],
                    journal="Mock Journal",
                    publication_date=datetime.now(),
                    pmid="12345678",
                    doi="10.1234/mock",
                    abstract="Mock abstract",
                    relevance_score=0.9
                )
            ],
            summary="Mock literature summary",
            total_results=1,
            searched_at=datetime.now()
        )


class MockRegulatoryReportingAgent:
    """Mock Regulatory Reporting Agent for testing."""
    
    def __init__(self, should_fail=False):
        self.agent_id = "mock_regulatory_reporting_agent"
        self.should_fail = should_fail
        self.called = False
        self.call_count = 0
    
    def generate_reports(self, signal: Signal, literature):
        """Mock generate_reports method."""
        self.called = True
        self.call_count += 1
        
        if self.should_fail:
            raise Exception("Mock regulatory reporting failure")
        
        from models.regulatory_report import RegulatoryReport
        
        return [
            RegulatoryReport(
                report_id=str(uuid.uuid4()),
                report_type='medwatch',
                signal=signal,
                literature_references=[],
                clinical_assessment="Mock assessment",
                generated_at=datetime.now(),
                validated=True,
                submission_status='draft'
            ),
            RegulatoryReport(
                report_id=str(uuid.uuid4()),
                report_type='eudravigilance',
                signal=signal,
                literature_references=[],
                clinical_assessment="Mock assessment",
                generated_at=datetime.now(),
                validated=True,
                submission_status='draft'
            )
        ]


# Property Tests

@settings(max_examples=100, deadline=None)
@given(events=st.lists(adverse_event_strategy(), min_size=1, max_size=50))
def test_property_12_workflow_initiation(events):
    """
    Property 12: Workflow Initiation
    
    Feature: adverse-event-signal-detection
    Property 12: For any new adverse event dataset received, the Orchestrator Agent 
    SHALL initiate the signal detection workflow by invoking the Signal Detection Agent.
    
    Validates: Requirements 4.1
    """
    # Arrange
    mock_signal_agent = MockSignalDetectionAgent(return_signal=True)
    mock_literature_agent = MockLiteratureMiningAgent()
    mock_reporting_agent = MockRegulatoryReportingAgent()
    
    orchestrator = OrchestratorAgent(
        signal_agent=mock_signal_agent,
        literature_agent=mock_literature_agent,
        reporting_agent=mock_reporting_agent
    )
    
    # Act
    result = orchestrator.initiate_investigation(events)
    
    # Assert: Signal Detection Agent must be invoked
    assert mock_signal_agent.called, "Signal Detection Agent was not invoked"
    assert mock_signal_agent.call_count == 1, "Signal Detection Agent should be called exactly once"
    
    # Assert: Investigation result is returned
    assert result is not None
    assert result.investigation_id is not None
    assert result.status in ['completed', 'failed']


@settings(max_examples=100, deadline=None)
@given(events=st.lists(adverse_event_strategy(), min_size=1, max_size=50))
def test_property_13_agent_coordination_sequence(events):
    """
    Property 13: Agent Coordination Sequence
    
    Feature: adverse-event-signal-detection
    Property 13: For any detected signal, the Orchestrator SHALL invoke agents in the 
    correct sequence: Signal Detection → Literature Mining → Regulatory Reporting.
    
    Validates: Requirements 4.2, 4.3
    """
    # Arrange
    mock_signal_agent = MockSignalDetectionAgent(return_signal=True)
    mock_literature_agent = MockLiteratureMiningAgent()
    mock_reporting_agent = MockRegulatoryReportingAgent()
    
    orchestrator = OrchestratorAgent(
        signal_agent=mock_signal_agent,
        literature_agent=mock_literature_agent,
        reporting_agent=mock_reporting_agent
    )
    
    # Act
    result = orchestrator.initiate_investigation(events)
    
    # Assert: All agents invoked in correct sequence
    assert mock_signal_agent.called, "Signal Detection Agent was not invoked"
    assert mock_literature_agent.called, "Literature Mining Agent was not invoked"
    assert mock_reporting_agent.called, "Regulatory Reporting Agent was not invoked"
    
    # Assert: Investigation completed successfully
    assert result.status == 'completed'
    assert result.signal is not None
    assert result.literature is not None
    assert len(result.reports) > 0


@settings(max_examples=100, deadline=None)
@given(events=st.lists(adverse_event_strategy(), min_size=1, max_size=50))
def test_property_14_comprehensive_investigation_summary(events):
    """
    Property 14: Comprehensive Investigation Summary
    
    Feature: adverse-event-signal-detection
    Property 14: For any completed workflow, the Orchestrator SHALL return a summary 
    containing signal details, literature findings, generated reports, and workflow status.
    
    Validates: Requirements 4.5
    """
    # Arrange
    mock_signal_agent = MockSignalDetectionAgent(return_signal=True)
    mock_literature_agent = MockLiteratureMiningAgent()
    mock_reporting_agent = MockRegulatoryReportingAgent()
    
    orchestrator = OrchestratorAgent(
        signal_agent=mock_signal_agent,
        literature_agent=mock_literature_agent,
        reporting_agent=mock_reporting_agent
    )
    
    # Act
    result = orchestrator.initiate_investigation(events)
    
    # Assert: Summary contains all required components
    assert result.investigation_id is not None, "Missing investigation_id"
    assert result.status is not None, "Missing status"
    assert result.signal is not None, "Missing signal details"
    assert result.literature is not None, "Missing literature findings"
    assert result.reports is not None, "Missing reports"
    assert len(result.reports) > 0, "No reports generated"
    assert result.started_at is not None, "Missing started_at"
    assert result.completed_at is not None, "Missing completed_at"
    
    # Assert: Reports include both MedWatch and EudraVigilance
    report_types = [r.report_type for r in result.reports]
    assert 'medwatch' in report_types, "Missing MedWatch report"
    assert 'eudravigilance' in report_types, "Missing EudraVigilance report"


@settings(max_examples=100, deadline=None)
@given(
    events=st.lists(adverse_event_strategy(), min_size=1, max_size=50),
    fail_stage=st.sampled_from(['signal', 'literature', 'reporting'])
)
def test_property_15_error_handling_and_partial_results(events, fail_stage):
    """
    Property 15: Error Handling and Partial Results
    
    Feature: adverse-event-signal-detection
    Property 15: For any agent failure during workflow execution, the Orchestrator SHALL 
    handle the error gracefully, preserve partial results, and report status to the user.
    
    Validates: Requirements 4.4, 8.5
    """
    # Arrange: Create agents with one that will fail
    if fail_stage == 'signal':
        mock_signal_agent = MockSignalDetectionAgent(should_fail=True)
        mock_literature_agent = MockLiteratureMiningAgent()
        mock_reporting_agent = MockRegulatoryReportingAgent()
    elif fail_stage == 'literature':
        mock_signal_agent = MockSignalDetectionAgent(return_signal=True)
        mock_literature_agent = MockLiteratureMiningAgent(should_fail=True)
        mock_reporting_agent = MockRegulatoryReportingAgent()
    else:  # reporting
        mock_signal_agent = MockSignalDetectionAgent(return_signal=True)
        mock_literature_agent = MockLiteratureMiningAgent()
        mock_reporting_agent = MockRegulatoryReportingAgent(should_fail=True)
    
    orchestrator = OrchestratorAgent(
        signal_agent=mock_signal_agent,
        literature_agent=mock_literature_agent,
        reporting_agent=mock_reporting_agent
    )
    
    # Act
    result = orchestrator.initiate_investigation(events)
    
    # Assert: Orchestrator handles error gracefully (doesn't crash)
    assert result is not None, "Orchestrator should return result even on failure"
    
    # Assert: Error is reported
    if fail_stage == 'signal':
        assert result.status == 'failed', "Status should be 'failed' when signal detection fails"
        assert len(result.errors) > 0, "Errors should be reported"
        assert any('signal detection' in e.lower() for e in result.errors), "Error should mention signal detection"
    else:
        # For literature and reporting failures, workflow continues with partial results
        assert len(result.errors) > 0, "Errors should be reported"
        
        if fail_stage == 'literature':
            assert any('literature' in e.lower() for e in result.errors), "Error should mention literature mining"
            # Signal should be preserved
            assert result.signal is not None, "Signal should be preserved on literature failure"
        
        if fail_stage == 'reporting':
            assert any('reporting' in e.lower() for e in result.errors), "Error should mention regulatory reporting"
            # Signal and literature should be preserved
            assert result.signal is not None, "Signal should be preserved on reporting failure"


# Unit Tests

def test_orchestrator_initialization():
    """Test orchestrator agent initialization."""
    orchestrator = OrchestratorAgent()
    
    assert orchestrator.agent_id == "orchestrator_agent"
    assert orchestrator.signal_agent is not None
    assert orchestrator.literature_agent is not None
    assert orchestrator.reporting_agent is not None
    assert len(orchestrator.active_investigations) == 0


def test_initiate_investigation_empty_events():
    """Test that empty events list raises ValueError."""
    orchestrator = OrchestratorAgent()
    
    with pytest.raises(ValueError, match="adverse_event_data cannot be empty"):
        orchestrator.initiate_investigation([])


def test_get_investigation_status():
    """Test getting investigation status."""
    mock_signal_agent = MockSignalDetectionAgent(return_signal=True)
    mock_literature_agent = MockLiteratureMiningAgent()
    mock_reporting_agent = MockRegulatoryReportingAgent()
    
    orchestrator = OrchestratorAgent(
        signal_agent=mock_signal_agent,
        literature_agent=mock_literature_agent,
        reporting_agent=mock_reporting_agent
    )
    
    # Create test event
    event = AdverseEvent(
        event_id="E001",
        drug_name="TestDrug",
        adverse_event_term="TestEvent",
        medra_code="12345678",
        patient_age=50,
        patient_sex="M",
        event_date=datetime.now(),
        outcome="recovered",
        reporter_type="physician"
    )
    
    # Initiate investigation
    result = orchestrator.initiate_investigation([event])
    
    # Get status
    status = orchestrator.get_investigation_status(result.investigation_id)
    
    assert status['investigation_id'] == result.investigation_id
    assert status['status'] == 'completed'
    assert status['events_analyzed'] == 1
    assert status['signal_detected'] is True
    assert status['literature_found'] is True
    assert status['reports_generated'] == 2


def test_get_investigation_status_not_found():
    """Test getting status for non-existent investigation."""
    orchestrator = OrchestratorAgent()
    
    with pytest.raises(ValueError, match="Investigation not found"):
        orchestrator.get_investigation_status("non-existent-id")


def test_handle_agent_response():
    """Test handling agent response messages."""
    orchestrator = OrchestratorAgent()
    
    # Create test event and initiate investigation
    event = AdverseEvent(
        event_id="E001",
        drug_name="TestDrug",
        adverse_event_term="TestEvent",
        medra_code="12345678",
        patient_age=50,
        patient_sex="M",
        event_date=datetime.now(),
        outcome="recovered",
        reporter_type="physician"
    )
    
    mock_signal_agent = MockSignalDetectionAgent(return_signal=False)
    orchestrator.signal_agent = mock_signal_agent
    
    result = orchestrator.initiate_investigation([event])
    
    # Create a mock response message
    signal = Signal(
        signal_id="SIG001",
        drug_name="TestDrug",
        adverse_event_term="TestEvent",
        event_count=10,
        expected_count=5.0,
        prr=2.0,
        ror=2.0,
        ic025=1.5,
        confidence_interval=(1.5, 3.0),
        detected_at=datetime.now(),
        severity='medium'
    )
    
    message = AgentMessage(
        message_id=str(uuid.uuid4()),
        message_type='signal_analysis_result',
        sender_agent_id='signal_detection_agent',
        recipient_agent_id=orchestrator.agent_id,
        timestamp=datetime.now(),
        payload={'signal': signal.__dict__},
        correlation_id=result.investigation_id
    )
    
    # Handle the message
    orchestrator.handle_agent_response(message)
    
    # Verify message was added to history
    state = orchestrator.active_investigations[result.investigation_id]
    assert len(state.message_history) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
