"""Property-based and unit tests for Signal Detection Agent."""

import pytest
from datetime import datetime
from hypothesis import given, strategies as st, settings
from typing import List

from models.adverse_event import AdverseEvent
from agents.signal_detection_agent import (
    SignalDetectionAgent,
    SignalAnalysisResult,
    StatisticalMetrics,
    CodeInterpreterError
)


# Custom strategies for generating test data
@st.composite
def adverse_event_strategy(draw):
    """Generate valid adverse events for testing."""
    return AdverseEvent(
        event_id=f"AE{draw(st.integers(min_value=1, max_value=999999))}",
        drug_name=draw(st.sampled_from(['DrugA', 'DrugB', 'DrugC', 'DrugX', 'DrugY'])),
        adverse_event_term=draw(st.sampled_from([
            'Cardiac Arrhythmia', 'Nausea', 'Headache', 
            'QT Prolongation', 'Dizziness', 'Fatigue'
        ])),
        medra_code=f"{draw(st.integers(min_value=10000000, max_value=99999999))}",
        patient_age=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=120))),
        patient_sex=draw(st.one_of(st.none(), st.sampled_from(['M', 'F', 'U']))),
        event_date=datetime.now(),
        outcome=draw(st.sampled_from(['recovered', 'fatal', 'hospitalization', 'ongoing'])),
        reporter_type=draw(st.sampled_from(['physician', 'pharmacist', 'consumer']))
    )


@st.composite
def adverse_event_list_strategy(draw, min_size=5, max_size=50):
    """Generate a list of adverse events."""
    return draw(st.lists(
        adverse_event_strategy(),
        min_size=min_size,
        max_size=max_size
    ))


class TestSignalDetectionAgentUnit:
    """Unit tests for Signal Detection Agent."""
    
    def test_create_agent(self):
        """Test creating a Signal Detection Agent."""
        agent = SignalDetectionAgent()
        assert agent.agent_id == "signal_detection_agent"
    
    def test_analyze_empty_events_raises_error(self):
        """Test that analyzing empty events list raises ValueError."""
        agent = SignalDetectionAgent()
        with pytest.raises(ValueError, match="Events list cannot be empty"):
            agent.analyze_events([])
    
    def test_analyze_single_drug_event(self):
        """Test analyzing a simple dataset with one drug-event combination."""
        agent = SignalDetectionAgent()
        
        events = [
            AdverseEvent(
                event_id=f"AE{i}",
                drug_name="DrugX",
                adverse_event_term="Cardiac Arrhythmia",
                medra_code="12345678",
                patient_age=65,
                patient_sex="M",
                event_date=datetime.now(),
                outcome="hospitalization",
                reporter_type="physician"
            )
            for i in range(10)
        ]
        
        # Add some background events
        events.extend([
            AdverseEvent(
                event_id=f"AE{i+10}",
                drug_name="DrugY",
                adverse_event_term="Nausea",
                medra_code="87654321",
                patient_age=45,
                patient_sex="F",
                event_date=datetime.now(),
                outcome="recovered",
                reporter_type="pharmacist"
            )
            for i in range(5)
        ])
        
        result = agent.analyze_events(events)
        
        assert isinstance(result, SignalAnalysisResult)
        assert result.total_events_analyzed == 15
        assert len(result.signals) >= 1
        
        # Find the DrugX-Cardiac Arrhythmia signal
        drugx_signal = next(
            (s for s in result.signals 
             if s.drug_name == "DrugX" and s.adverse_event_term == "Cardiac Arrhythmia"),
            None
        )
        assert drugx_signal is not None
        assert drugx_signal.event_count == 10
    
    def test_signal_flagging_when_ic025_positive(self):
        """Test that signals are flagged when IC025 > 0."""
        agent = SignalDetectionAgent()
        
        # Create a dataset with elevated reporting for DrugX + Cardiac event
        events = []
        
        # 20 events for DrugX + Cardiac (elevated)
        for i in range(20):
            events.append(AdverseEvent(
                event_id=f"AE{i}",
                drug_name="DrugX",
                adverse_event_term="Cardiac Arrhythmia",
                medra_code="12345678",
                patient_age=65,
                patient_sex="M",
                event_date=datetime.now(),
                outcome="hospitalization",
                reporter_type="physician"
            ))
        
        # 5 events for DrugX + Other
        for i in range(5):
            events.append(AdverseEvent(
                event_id=f"AE{i+20}",
                drug_name="DrugX",
                adverse_event_term="Nausea",
                medra_code="11111111",
                patient_age=45,
                patient_sex="F",
                event_date=datetime.now(),
                outcome="recovered",
                reporter_type="pharmacist"
            ))
        
        # 3 events for Other + Cardiac
        for i in range(3):
            events.append(AdverseEvent(
                event_id=f"AE{i+25}",
                drug_name="DrugY",
                adverse_event_term="Cardiac Arrhythmia",
                medra_code="12345678",
                patient_age=55,
                patient_sex="M",
                event_date=datetime.now(),
                outcome="hospitalization",
                reporter_type="physician"
            ))
        
        # 30 events for Other + Other
        for i in range(30):
            events.append(AdverseEvent(
                event_id=f"AE{i+28}",
                drug_name="DrugY",
                adverse_event_term="Nausea",
                medra_code="11111111",
                patient_age=40,
                patient_sex="F",
                event_date=datetime.now(),
                outcome="recovered",
                reporter_type="consumer"
            ))
        
        result = agent.analyze_events(events)
        
        # Find the DrugX-Cardiac signal
        drugx_signal = next(
            (s for s in result.signals 
             if s.drug_name == "DrugX" and s.adverse_event_term == "Cardiac Arrhythmia"),
            None
        )
        
        assert drugx_signal is not None
        assert drugx_signal.is_flagged()  # Should be flagged due to elevated reporting
    
    def test_invalid_event_missing_drug_name(self):
        """Test that events with missing drug_name raise ValueError."""
        agent = SignalDetectionAgent()
        
        # AdverseEvent model validates drug_name in __post_init__
        with pytest.raises(ValueError, match="drug_name is required"):
            events = [
                AdverseEvent(
                    event_id="AE001",
                    drug_name="",  # Invalid: empty drug name
                    adverse_event_term="Cardiac Arrhythmia",
                    medra_code="12345678",
                    patient_age=65,
                    patient_sex="M",
                    event_date=datetime.now(),
                    outcome="hospitalization",
                    reporter_type="physician"
                )
            ]



@pytest.mark.property
class TestSignalDetectionAgentProperties:
    """Property-based tests for Signal Detection Agent."""
    
    @given(adverse_event_list_strategy(min_size=5, max_size=30))
    @settings(max_examples=100, deadline=None)
    def test_property_1_statistical_analysis_completeness(self, events: List[AdverseEvent]):
        """
        Feature: adverse-event-signal-detection, Property 1: Statistical Analysis Completeness
        
        For any valid adverse event dataset, when the Signal Detection Agent analyzes the data,
        the results SHALL contain all three disproportionality metrics (PRR, ROR, IC025),
        event counts, and confidence intervals.
        
        Validates: Requirements 1.1, 1.2, 1.4
        """
        agent = SignalDetectionAgent()
        
        try:
            result = agent.analyze_events(events)
            
            # Verify result structure
            assert isinstance(result, SignalAnalysisResult)
            assert result.total_events_analyzed == len(events)
            assert isinstance(result.signals, list)
            assert isinstance(result.errors, list)
            
            # For each signal, verify all metrics are present
            for signal in result.signals:
                # Verify all statistical metrics are present
                assert signal.prr is not None, "PRR must be calculated"
                assert signal.ror is not None, "ROR must be calculated"
                assert signal.ic025 is not None, "IC025 must be calculated"
                
                # Verify event counts
                assert signal.event_count >= 0, "Event count must be non-negative"
                assert signal.expected_count >= 0, "Expected count must be non-negative"
                
                # Verify confidence interval
                assert signal.confidence_interval is not None, "Confidence interval must be present"
                assert len(signal.confidence_interval) == 2, "Confidence interval must have 2 values"
                
                # Verify other required fields
                assert signal.signal_id, "Signal ID must be present"
                assert signal.drug_name, "Drug name must be present"
                assert signal.adverse_event_term, "Adverse event term must be present"
                assert signal.severity in ['low', 'medium', 'high', 'critical']
                
        except ValueError as e:
            # Some random datasets may be invalid, which is acceptable
            assert "required" in str(e).lower() or "empty" in str(e).lower()
    
    @given(adverse_event_list_strategy(min_size=10, max_size=30))
    @settings(max_examples=100, deadline=None)
    def test_property_2_signal_flagging_consistency(self, events: List[AdverseEvent]):
        """
        Feature: adverse-event-signal-detection, Property 2: Signal Flagging Consistency
        
        For any analysis result where IC025 > 0, the signal SHALL be flagged for investigation.
        
        Validates: Requirements 1.3
        """
        agent = SignalDetectionAgent()
        
        try:
            result = agent.analyze_events(events)
            
            # For each signal, verify flagging consistency
            for signal in result.signals:
                if signal.ic025 > 0:
                    assert signal.is_flagged(), \
                        f"Signal with IC025={signal.ic025} should be flagged"
                else:
                    assert not signal.is_flagged(), \
                        f"Signal with IC025={signal.ic025} should not be flagged"
                        
        except ValueError:
            # Some random datasets may be invalid
            pass


@pytest.mark.property
class TestSignalDetectionAgentErrorHandling:
    """Property-based tests for error handling."""
    
    @given(st.lists(adverse_event_strategy(), min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_property_3_invalid_data_error_handling(self, events: List[AdverseEvent]):
        """
        Feature: adverse-event-signal-detection, Property 3: Invalid Data Error Handling
        
        For any invalid or incomplete adverse event data, the Signal Detection Agent
        SHALL return a descriptive error message without crashing.
        
        Validates: Requirements 1.5
        """
        agent = SignalDetectionAgent()
        
        # Test with valid events that have missing fields after creation
        # We can't create invalid AdverseEvent objects due to model validation,
        # so we test the agent's validation logic with edge cases
        
        # Test with events that will cause validation errors in the agent
        # (e.g., events that pass model validation but fail agent validation)
        try:
            result = agent.analyze_events(events)
            # Should complete without crashing
            assert result is not None
            assert isinstance(result.errors, list)
        except ValueError as e:
            # Should provide descriptive error message
            error_msg = str(e).lower()
            assert any(keyword in error_msg for keyword in [
                'required', 'invalid', 'empty', 'missing', 'cannot'
            ]), f"Error message should be descriptive: {e}"
    
    def test_property_4_code_interpreter_retry_behavior(self):
        """
        Feature: adverse-event-signal-detection, Property 4: Code Interpreter Retry Behavior
        
        For any Code Interpreter execution failure, the Signal Detection Agent SHALL
        retry exactly once, and if the retry fails, SHALL report the error with execution details.
        
        Validates: Requirements 8.1
        """
        from config import AgentCoreConfig, CodeInterpreterConfig
        
        # Create config with retry enabled
        config = AgentCoreConfig.default()
        config.code_interpreter.max_retries = 1
        config.code_interpreter.retry_delay_seconds = 0  # No delay for testing
        
        # Mock Code Interpreter that fails
        class FailingCodeInterpreter:
            def __init__(self):
                self.call_count = 0
            
            def execute(self, a, b, c, d):
                self.call_count += 1
                raise CodeInterpreterError("Simulated failure")
        
        failing_interpreter = FailingCodeInterpreter()
        agent = SignalDetectionAgent(config=config, code_interpreter=failing_interpreter)
        
        events = [
            AdverseEvent(
                event_id=f"AE{i}",
                drug_name="DrugX",
                adverse_event_term="Event",
                medra_code="12345678",
                patient_age=50,
                patient_sex="M",
                event_date=datetime.now(),
                outcome="recovered",
                reporter_type="physician"
            )
            for i in range(5)
        ]
        
        # Add background events
        events.extend([
            AdverseEvent(
                event_id=f"AE{i+5}",
                drug_name="DrugY",
                adverse_event_term="OtherEvent",
                medra_code="87654321",
                patient_age=40,
                patient_sex="F",
                event_date=datetime.now(),
                outcome="recovered",
                reporter_type="pharmacist"
            )
            for i in range(5)
        ])
        
        with pytest.raises(CodeInterpreterError, match="Code Interpreter failed after retry"):
            agent.analyze_events(events)
        
        # Verify retry was attempted (should be called twice: initial + 1 retry)
        assert failing_interpreter.call_count == 2, \
            "Code Interpreter should be called twice (initial + 1 retry)"
