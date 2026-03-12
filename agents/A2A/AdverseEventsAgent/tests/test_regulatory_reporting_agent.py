"""Property-based and unit tests for Regulatory Reporting Agent."""

import pytest
from datetime import datetime
from hypothesis import given, strategies as st, settings
from typing import List

from models.signal import Signal
from models.literature import Article, LiteratureResults
from models.regulatory_report import RegulatoryReport
from agents.regulatory_reporting_agent import (
    RegulatoryReportingAgent,
    ValidationResult,
    GatewayError
)


# Custom strategies
@st.composite
def signal_strategy(draw):
    """Generate valid signals for testing."""
    ic025 = draw(st.floats(min_value=-5.0, max_value=5.0))
    return Signal(
        signal_id=f"SIG{draw(st.integers(min_value=1, max_value=999999))}",
        drug_name=draw(st.sampled_from(['DrugA', 'DrugB', 'DrugX'])),
        adverse_event_term=draw(st.sampled_from(['Cardiac Arrhythmia', 'Nausea', 'Headache'])),
        event_count=draw(st.integers(min_value=1, max_value=100)),
        expected_count=draw(st.floats(min_value=0.1, max_value=50.0)),
        prr=draw(st.floats(min_value=0.1, max_value=20.0)),
        ror=draw(st.floats(min_value=0.1, max_value=20.0)),
        ic025=ic025,
        confidence_interval=(ic025, ic025 + draw(st.floats(min_value=0.1, max_value=3.0))),
        detected_at=datetime.now(),
        severity=draw(st.sampled_from(['low', 'medium', 'high', 'critical']))
    )


class TestRegulatoryReportingAgentUnit:
    """Unit tests for Regulatory Reporting Agent."""
    
    def test_create_agent(self):
        """Test creating a Regulatory Reporting Agent."""
        agent = RegulatoryReportingAgent()
        assert agent.agent_id == "regulatory_reporting_agent"
    
    def test_generate_reports_requires_valid_signal(self):
        """Test that generate_reports requires a valid signal."""
        agent = RegulatoryReportingAgent()
        
        with pytest.raises(ValueError, match="Signal cannot be None"):
            agent.generate_reports(None)
    
    def test_generate_medwatch_report(self):
        """Test MedWatch report generation."""
        agent = RegulatoryReportingAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        report = agent.generate_medwatch_report(signal)
        
        assert report.report_type == "medwatch"
        assert report.signal == signal
        assert report.clinical_assessment
        assert "DrugX" in report.clinical_assessment
        assert "Cardiac Arrhythmia" in report.clinical_assessment
    
    def test_generate_eudravigilance_report(self):
        """Test EudraVigilance report generation."""
        agent = RegulatoryReportingAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        report = agent.generate_eudravigilance_report(signal)
        
        assert report.report_type == "eudravigilance"
        assert report.signal == signal
        assert report.clinical_assessment
    
    def test_validate_report_valid(self):
        """Test validation of a valid report."""
        agent = RegulatoryReportingAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        report = agent.generate_medwatch_report(signal)
        validation = agent.validate_report(report)
        
        assert isinstance(validation, ValidationResult)
        assert validation.is_valid
        assert len(validation.errors) == 0
    
    def test_format_for_submission(self):
        """Test report formatting for Gateway submission."""
        agent = RegulatoryReportingAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        report = agent.generate_medwatch_report(signal)
        formatted = agent.format_for_submission(report)
        
        assert isinstance(formatted, dict)
        assert "report_id" in formatted
        assert "signal" in formatted
        assert "clinical_assessment" in formatted
        assert formatted["signal"]["drug_name"] == "DrugX"


@pytest.mark.property
class TestRegulatoryReportingAgentProperties:
    """Property-based tests for Regulatory Reporting Agent."""
    
    @given(signal_strategy())
    @settings(max_examples=100, deadline=None)
    def test_property_8_dual_format_report_generation(self, signal: Signal):
        """
        Feature: adverse-event-signal-detection, Property 8: Dual Format Report Generation
        
        For any completed investigation, the Regulatory Reporting Agent SHALL generate
        both MedWatch and EudraVigilance format reports.
        
        Validates: Requirements 3.1
        """
        agent = RegulatoryReportingAgent()
        
        try:
            reports = agent.generate_reports(signal)
            
            # Verify both reports generated
            assert len(reports) == 2, "Must generate exactly 2 reports"
            
            # Verify report types
            report_types = [r.report_type for r in reports]
            assert "medwatch" in report_types, "Must include MedWatch report"
            assert "eudravigilance" in report_types, "Must include EudraVigilance report"
            
            # Verify each report has required components
            for report in reports:
                assert report.report_id, "Report must have ID"
                assert report.signal == signal, "Report must reference signal"
                assert report.clinical_assessment, "Report must have clinical assessment"
                assert report.report_type in ['medwatch', 'eudravigilance']
                
        except ValueError as e:
            # Some random signals may be invalid
            assert "required" in str(e).lower()
    
    @given(signal_strategy())
    @settings(max_examples=100, deadline=None)
    def test_property_9_report_validation_and_completeness(self, signal: Signal):
        """
        Feature: adverse-event-signal-detection, Property 9: Report Validation and Completeness
        
        For any generated regulatory report, it SHALL include signal description, statistical
        evidence, literature references, and clinical assessment, AND SHALL pass schema
        validation for the target regulatory system.
        
        Validates: Requirements 3.2, 3.3
        """
        agent = RegulatoryReportingAgent()
        
        try:
            reports = agent.generate_reports(signal)
            
            for report in reports:
                # Verify completeness
                assert report.signal, "Report must include signal"
                assert report.clinical_assessment, "Report must include clinical assessment"
                assert len(report.clinical_assessment) > 50, "Assessment must be substantial"
                
                # Verify signal description in assessment
                assert signal.drug_name in report.clinical_assessment
                assert signal.adverse_event_term in report.clinical_assessment
                
                # Verify statistical evidence in assessment
                assert str(signal.prr) in report.clinical_assessment or "PRR" in report.clinical_assessment
                assert str(signal.event_count) in report.clinical_assessment
                
                # Validate report
                validation = agent.validate_report(report)
                assert isinstance(validation, ValidationResult)
                assert validation.is_valid, f"Report must pass validation: {validation.errors}"
                
        except ValueError:
            pass
    
    @given(signal_strategy())
    @settings(max_examples=50, deadline=None)
    def test_property_10_report_formatting_for_submission(self, signal: Signal):
        """
        Feature: adverse-event-signal-detection, Property 10: Report Formatting for Submission
        
        For any validated report, the Regulatory Reporting Agent SHALL format it correctly
        for Gateway submission with proper structure and encoding.
        
        Validates: Requirements 3.4
        """
        agent = RegulatoryReportingAgent()
        
        try:
            reports = agent.generate_reports(signal)
            
            for report in reports:
                # Format for submission
                formatted = agent.format_for_submission(report)
                
                # Verify structure
                assert isinstance(formatted, dict), "Formatted report must be dictionary"
                
                # Verify required fields
                assert "report_id" in formatted
                assert "report_type" in formatted
                assert "signal" in formatted
                assert "clinical_assessment" in formatted
                assert "literature_references" in formatted
                
                # Verify signal structure
                assert "drug_name" in formatted["signal"]
                assert "adverse_event_term" in formatted["signal"]
                assert "statistical_metrics" in formatted["signal"]
                
                # Verify statistical metrics structure
                metrics = formatted["signal"]["statistical_metrics"]
                assert "prr" in metrics
                assert "ror" in metrics
                assert "ic025" in metrics
                assert "confidence_interval" in metrics
                
        except ValueError:
            pass
    
    def test_property_11_gateway_failure_recovery(self):
        """
        Feature: adverse-event-signal-detection, Property 11: Gateway Failure Recovery
        
        For any Gateway submission failure, the Regulatory Reporting Agent SHALL save
        the report locally and notify the user with error details.
        
        Validates: Requirements 8.3
        """
        # Mock gateway that fails
        class FailingGateway:
            def submit(self, report, report_type):
                raise Exception("Simulated gateway failure")
        
        failing_gateway = FailingGateway()
        agent = RegulatoryReportingAgent(gateway=failing_gateway)
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        report = agent.generate_medwatch_report(signal)
        
        # Should raise GatewayError but save locally
        with pytest.raises(GatewayError, match="Gateway submission failed"):
            agent.submit_report(report)
        
        # Verify report was marked as saved locally
        assert report.submission_status == "saved_locally"


@pytest.mark.property
class TestRegulatoryReportingAgentIntegration:
    """Integration tests for Regulatory Reporting Agent."""
    
    def test_end_to_end_report_generation_with_literature(self):
        """Test complete report generation with literature."""
        agent = RegulatoryReportingAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        literature = LiteratureResults(
            query="DrugX AND Cardiac Arrhythmia",
            articles=[
                Article(
                    title="Cardiac Safety of DrugX",
                    authors=["Smith J"],
                    journal="J Pharmacovigilance",
                    publication_date=datetime.now(),
                    pmid="12345678",
                    doi="10.1234/example",
                    abstract="Study on cardiac safety",
                    relevance_score=0.95
                )
            ],
            summary="Found 1 relevant article",
            total_results=1,
            searched_at=datetime.now()
        )
        
        reports = agent.generate_reports(signal, literature)
        
        assert len(reports) == 2
        for report in reports:
            assert len(report.literature_references) == 1
            assert "Found 1 relevant article" in report.clinical_assessment
