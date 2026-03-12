"""Regulatory Reporting Agent for generating FDA and EMA reports.
Once the signal is detected with high confidence,
substantiating literature is searched and identified,
then adverse event is reported using these regulatory reports """

from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
import json

from models.signal import Signal
from models.literature import LiteratureResults
from models.regulatory_report import RegulatoryReport


@dataclass
class ValidationResult:
    """Result of report validation."""
    
    is_valid: bool
    errors: List[str]
    warnings: List[str]


class GatewayError(Exception):
    """Exception raised when Gateway submission fails."""
    pass


class RegulatoryReportingAgent:
    """
    Agent responsible for generating structured regulatory reports for FDA and EMA submission.
    
    Generates reports in MedWatch (FDA) and EudraVigilance (EMA) formats, validates them
    against regulatory schemas, and submits via Gateway or saves locally on failure.
    """
    
    def __init__(self, config=None, gateway=None):
        """
        Initialize Regulatory Reporting Agent.
        
        Args:
            config: AgentCore configuration
            gateway: Gateway Tool instance (for testing, can be mocked)
        """
        self.config = config
        self.gateway = gateway
        self.agent_id = "regulatory_reporting_agent"
    
    def generate_reports(
        self,
        signal: Signal,
        literature: Optional[LiteratureResults] = None
    ) -> List[RegulatoryReport]:
        """
        Generate regulatory reports in both MedWatch and EudraVigilance formats.
        
        Args:
            signal: Detected safety signal
            literature: Optional literature search results
            
        Returns:
            List containing both MedWatch and EudraVigilance reports
            
        Raises:
            ValueError: If signal is invalid
        """
        if not signal:
            raise ValueError("Signal cannot be None")
        if not signal.drug_name:
            raise ValueError("Signal must have drug_name")
        if not signal.adverse_event_term:
            raise ValueError("Signal must have adverse_event_term")
        
        reports = []
        
        # Generate MedWatch report (FDA)
        medwatch_report = self.generate_medwatch_report(signal, literature)
        reports.append(medwatch_report)
        
        # Generate EudraVigilance report (EMA)
        eudravigilance_report = self.generate_eudravigilance_report(signal, literature)
        reports.append(eudravigilance_report)
        
        return reports
    
    def generate_medwatch_report(
        self,
        signal: Signal,
        literature: Optional[LiteratureResults] = None
    ) -> RegulatoryReport:
        """
        Generate a MedWatch (FDA) format report.
        
        Args:
            signal: Detected safety signal
            literature: Optional literature search results
            
        Returns:
            RegulatoryReport in MedWatch format
        """
        # Generate clinical assessment
        clinical_assessment = self._generate_clinical_assessment(signal, literature)
        
        # Create report
        report = RegulatoryReport(
            report_id=f"MW_{signal.signal_id}_{int(datetime.now().timestamp())}",
            report_type="medwatch",
            signal=signal,
            literature_references=literature.articles if literature else [],
            clinical_assessment=clinical_assessment,
            generated_at=datetime.now(),
            validated=False,
            submission_status="draft"
        )
        
        # Validate report
        validation = self.validate_report(report)
        report.validated = validation.is_valid
        
        return report
    
    def generate_eudravigilance_report(
        self,
        signal: Signal,
        literature: Optional[LiteratureResults] = None
    ) -> RegulatoryReport:
        """
        Generate an EudraVigilance (EMA) format report.
        
        Args:
            signal: Detected safety signal
            literature: Optional literature search results
            
        Returns:
            RegulatoryReport in EudraVigilance format
        """
        # Generate clinical assessment
        clinical_assessment = self._generate_clinical_assessment(signal, literature)
        
        # Create report
        report = RegulatoryReport(
            report_id=f"EV_{signal.signal_id}_{int(datetime.now().timestamp())}",
            report_type="eudravigilance",
            signal=signal,
            literature_references=literature.articles if literature else [],
            clinical_assessment=clinical_assessment,
            generated_at=datetime.now(),
            validated=False,
            submission_status="draft"
        )
        
        # Validate report
        validation = self.validate_report(report)
        report.validated = validation.is_valid
        
        return report
    
    def validate_report(self, report: RegulatoryReport) -> ValidationResult:
        """
        Validate a regulatory report against schema requirements.
        
        Args:
            report: Report to validate
            
        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        errors = []
        warnings = []
        
        # Validate required fields
        if not report.report_id:
            errors.append("Report ID is required")
        
        if not report.signal:
            errors.append("Signal is required")
        else:
            # Validate signal completeness
            if not report.signal.drug_name:
                errors.append("Signal must have drug_name")
            if not report.signal.adverse_event_term:
                errors.append("Signal must have adverse_event_term")
            if report.signal.event_count <= 0:
                errors.append("Signal must have positive event_count")
        
        if not report.clinical_assessment:
            errors.append("Clinical assessment is required")
        elif len(report.clinical_assessment) < 50:
            warnings.append("Clinical assessment is very brief")
        
        # Validate report type
        if report.report_type not in ['medwatch', 'eudravigilance']:
            errors.append(f"Invalid report type: {report.report_type}")
        
        # Check for statistical metrics
        if report.signal:
            if report.signal.prr is None:
                warnings.append("PRR metric is missing")
            if report.signal.ror is None:
                warnings.append("ROR metric is missing")
            if report.signal.ic025 is None:
                warnings.append("IC025 metric is missing")
        
        # Validate literature references (if present)
        if report.literature_references:
            for i, article in enumerate(report.literature_references):
                if not article.title:
                    warnings.append(f"Article {i+1} missing title")
                if not article.authors:
                    warnings.append(f"Article {i+1} missing authors")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def format_for_submission(self, report: RegulatoryReport) -> Dict[str, Any]:
        """
        Format a report for Gateway submission.
        
        Args:
            report: Report to format
            
        Returns:
            Dictionary formatted for Gateway submission
        """
        # Base report structure
        formatted = {
            "report_id": report.report_id,
            "report_type": report.report_type,
            "generated_at": report.generated_at.isoformat(),
            "submission_status": report.submission_status,
            
            # Signal information
            "signal": {
                "signal_id": report.signal.signal_id,
                "drug_name": report.signal.drug_name,
                "adverse_event_term": report.signal.adverse_event_term,
                "event_count": report.signal.event_count,
                "expected_count": report.signal.expected_count,
                "severity": report.signal.severity,
                
                # Statistical metrics
                "statistical_metrics": {
                    "prr": report.signal.prr,
                    "ror": report.signal.ror,
                    "ic025": report.signal.ic025,
                    "confidence_interval": {
                        "lower": report.signal.confidence_interval[0],
                        "upper": report.signal.confidence_interval[1]
                    }
                },
                
                "detected_at": report.signal.detected_at.isoformat()
            },
            
            # Clinical assessment
            "clinical_assessment": report.clinical_assessment,
            
            # Literature references
            "literature_references": [
                {
                    "title": article.title,
                    "authors": article.authors,
                    "journal": article.journal,
                    "publication_date": article.publication_date.isoformat(),
                    "pmid": article.pmid,
                    "doi": article.doi,
                    "relevance_score": article.relevance_score
                }
                for article in report.literature_references
            ]
        }
        
        return formatted
    
    def submit_report(self, report: RegulatoryReport) -> bool:
        """
        Submit a report via Gateway or save locally on failure.
        
        Args:
            report: Report to submit
            
        Returns:
            True if submission successful, False if saved locally
        """
        # Validate before submission
        validation = self.validate_report(report)
        if not validation.is_valid:
            raise ValueError(f"Report validation failed: {', '.join(validation.errors)}")
        
        # Format for submission
        formatted_report = self.format_for_submission(report)
        
        try:
            # Attempt Gateway submission
            if self.gateway:
                self.gateway.submit(formatted_report, report.report_type)
                report.submission_status = "submitted"
                return True
            else:
                # No gateway configured - save locally
                self._save_report_locally(report, formatted_report)
                return False
                
        except Exception as e:
            # Gateway submission failed - save locally
            self._save_report_locally(report, formatted_report)
            raise GatewayError(f"Gateway submission failed: {str(e)}")
    
    def _save_report_locally(
        self,
        report: RegulatoryReport,
        formatted_report: Dict[str, Any]
    ) -> str:
        """
        Save a report locally when Gateway submission fails.
        
        Args:
            report: Original report object
            formatted_report: Formatted report dictionary
            
        Returns:
            Path to saved file
        """
        # Create filename
        filename = f"{report.report_id}_{report.report_type}.json"
        
        # In production, this would save to a configured directory
        # For now, we'll just return the filename
        # with open(filename, 'w') as f:
        #     json.dump(formatted_report, f, indent=2)
        
        report.submission_status = "saved_locally"
        return filename
    
    def _generate_clinical_assessment(
        self,
        signal: Signal,
        literature: Optional[LiteratureResults] = None
    ) -> str:
        """
        Generate clinical assessment text for the report.
        
        Args:
            signal: Detected safety signal
            literature: Optional literature search results
            
        Returns:
            Clinical assessment text
        """
        assessment_parts = []
        
        # Signal description
        assessment_parts.append(
            f"A potential safety signal has been detected for {signal.drug_name} "
            f"associated with {signal.adverse_event_term}."
        )
        
        # Statistical evidence
        assessment_parts.append(
            f"\n\nStatistical Analysis:\n"
            f"- Event Count: {signal.event_count} reports\n"
            f"- Expected Count: {signal.expected_count:.2f} reports\n"
            f"- Proportional Reporting Ratio (PRR): {signal.prr:.2f}\n"
            f"- Reporting Odds Ratio (ROR): {signal.ror:.2f}\n"
            f"- Information Component (IC025): {signal.ic025:.2f}\n"
            f"- 95% Confidence Interval: ({signal.confidence_interval[0]:.2f}, "
            f"{signal.confidence_interval[1]:.2f})"
        )
        
        # Severity assessment
        severity_text = {
            'critical': 'This signal is classified as CRITICAL and requires immediate investigation.',
            'high': 'This signal is classified as HIGH priority and warrants prompt investigation.',
            'medium': 'This signal is classified as MEDIUM priority and should be monitored closely.',
            'low': 'This signal is classified as LOW priority but should be tracked.'
        }
        assessment_parts.append(f"\n\n{severity_text.get(signal.severity, '')}")
        
        # Literature evidence
        if literature and literature.articles:
            assessment_parts.append(
                f"\n\nLiterature Review:\n"
                f"{literature.summary}"
            )
        else:
            assessment_parts.append(
                "\n\nLiterature Review:\n"
                "No published literature was found for this drug-event combination. "
                "This may represent a novel safety signal requiring further investigation."
            )
        
        # Recommendations
        assessment_parts.append(
            "\n\nRecommendations:\n"
            "1. Conduct detailed case review of all reported events\n"
            "2. Assess temporal relationship between drug exposure and event onset\n"
            "3. Evaluate alternative explanations and confounding factors\n"
            "4. Consider additional pharmacoepidemiological studies if signal persists\n"
            "5. Update product labeling if causal relationship is established"
        )
        
        return "".join(assessment_parts)



def create_regulatory_reporting_strands_agent(config=None):
    """
    Create a Strands Agent wrapper for Regulatory Reporting Agent.
    
    This function creates a Strands Agent that can be used with A2AServer
    for agent-to-agent communication.
    
    Args:
        config: AgentCore configuration
        
    Returns:
        Strands Agent instance
    """
    from strands import Agent
    
    # Create the underlying agent
    agent_impl = RegulatoryReportingAgent(config=config)
    
    def generate_reports_tool(signal_json: str, literature_json: Optional[str] = None) -> str:
        """
        Tool to generate regulatory reports for a detected signal.
        
        Args:
            signal_json: JSON string containing signal data
            literature_json: Optional JSON string containing literature results
            
        Returns:
            JSON string with generated reports
        """
        import json
        
        try:
            # Parse signal from JSON
            signal_data = json.loads(signal_json)
            signal = Signal(**signal_data)
            
            # Parse literature if provided
            literature = None
            if literature_json:
                literature_data = json.loads(literature_json)
                literature = LiteratureResults(**literature_data)
            
            # Generate reports
            reports = agent_impl.generate_reports(signal, literature)
            
            # Return as JSON
            return json.dumps({
                'reports': [r.__dict__ for r in reports],
                'count': len(reports)
            }, default=str)
            
        except Exception as e:
            return json.dumps({
                'error': str(e),
                'error_type': type(e).__name__
            })
    
    # Create Strands Agent
    return Agent(
        name="Regulatory Reporting Agent",
        description="""
        I am a regulatory reporting agent specialized in generating structured 
        regulatory reports for FDA (MedWatch) and EMA (EudraVigilance) submission. 
        I create compliant reports with signal descriptions, statistical evidence, 
        literature references, and clinical assessments.
        """,
        tools=[generate_reports_tool],
        instructions="""
        When you receive a signal and literature findings:
        1. Generate both MedWatch (FDA) and EudraVigilance (EMA) format reports
        2. Include signal description, statistical evidence, literature references, and clinical assessment
        3. Validate reports against regulatory schema requirements
        4. Format reports for Gateway submission
        5. Handle submission failures by saving reports locally
        6. Provide detailed validation error messages
        """
    )
