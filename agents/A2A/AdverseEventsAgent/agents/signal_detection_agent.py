"""Signal Detection Agent for adverse event analysis."""

import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import math

from models.adverse_event import AdverseEvent
from models.signal import Signal


@dataclass
class StatisticalMetrics:
    """Statistical metrics for signal detection."""
    prr: float  # Proportional Reporting Ratio
    ror: float  # Reporting Odds Ratio
    ic025: float  # Information Component lower bound
    confidence_interval: Tuple[float, float]
    event_count: int
    expected_count: float


@dataclass
class SignalAnalysisResult:
    """Result of signal detection analysis."""
    signals: List[Signal]
    total_events_analyzed: int
    analysis_timestamp: datetime
    errors: List[str]


class CodeInterpreterError(Exception):
    """Exception raised when Code Interpreter execution fails."""
    pass


class SignalDetectionAgent:
    """
    Agent responsible for analyzing adverse event reports using statistical methods.
    
    Uses Code Interpreter tool for statistical computations to detect safety signals
    using disproportionality analysis (PRR, ROR, IC025).
    PRR- proportional reporting ratio to identify potential safety issues by comparing
    frequency of adverse eventfor a drug against all other drugs in a database.
    ROR-reporting odds ratio detects safety signalby
    comparing occurence of specific adverse drug reaction for a drug against other drugs in a database.
    IC025 is lower limit of 95% CI for the informaton component- bayesian measure to detect safety signals
    by comparing observed vs expected drug-adverse reaction pairs
    """
    
    def __init__(self, config=None, code_interpreter=None):
        """
        Initialize Signal Detection Agent.
        
        Args:
            config: AgentCore configuration
            code_interpreter: Code Interpreter tool instance (for testing, can be mocked)
        """
        self.config = config
        self.code_interpreter = code_interpreter
        self.agent_id = "signal_detection_agent"
    
    def analyze_events(self, events: List[AdverseEvent]) -> SignalAnalysisResult:
        """
        Analyze adverse event data to detect potential safety signals.
        
        Args:
            events: List of adverse event reports
            
        Returns:
            SignalAnalysisResult containing detected signals
            
        Raises:
            ValueError: If events list is empty or invalid
        """
        # Validate input
        if not events:
            raise ValueError("Events list cannot be empty")
        
        errors = []
        signals = []
        
        try:
            # Validate all events
            self._validate_events(events)
            
            # Group events by drug-event combination
            drug_event_combinations = self._group_events(events)
            
            # Calculate disproportionality metrics for each combination
            for (drug, event_term), event_list in drug_event_combinations.items():
                try:
                    metrics = self.calculate_disproportionality(
                        drug=drug,
                        event=event_term,
                        events=events,
                        specific_events=event_list
                    )
                    
                    # Create signal object
                    signal = Signal(
                        signal_id=f"SIG_{drug}_{event_term}_{int(time.time())}",
                        drug_name=drug,
                        adverse_event_term=event_term,
                        event_count=metrics.event_count,
                        expected_count=metrics.expected_count,
                        prr=metrics.prr,
                        ror=metrics.ror,
                        ic025=metrics.ic025,
                        confidence_interval=metrics.confidence_interval,
                        detected_at=datetime.now(),
                        severity=self._determine_severity(metrics)
                    )
                    
                    signals.append(signal)
                    
                except CodeInterpreterError:
                    # Re-raise CodeInterpreterError (critical failure)
                    raise
                except Exception as e:
                    errors.append(f"Error analyzing {drug}-{event_term}: {str(e)}")
        
        except ValueError as e:
            errors.append(str(e))
            raise
        
        return SignalAnalysisResult(
            signals=signals,
            total_events_analyzed=len(events),
            analysis_timestamp=datetime.now(),
            errors=errors
        )
    
    def calculate_disproportionality(
        self,
        drug: str,
        event: str,
        events: List[AdverseEvent],
        specific_events: List[AdverseEvent]
    ) -> StatisticalMetrics:
        """
        Calculate disproportionality metrics (PRR, ROR, IC025) for a drug-event combination.
        
        Uses a 2x2 contingency table:
        - a = count of drug-event combination
        - b = count of drug with other events
        - c = count of event with other drugs
        - d = count of other drug-event combinations
        
        Args:
            drug: Drug name
            event: Adverse event term
            events: All adverse events
            specific_events: Events for this specific drug-event combination
            
        Returns:
            StatisticalMetrics with PRR, ROR, IC025, and confidence intervals
        """
        # Build contingency table
        a = len(specific_events)  # drug + event
        
        # Count drug with other events
        b = sum(1 for e in events if e.drug_name == drug and e.adverse_event_term != event)
        
        # Count event with other drugs
        c = sum(1 for e in events if e.drug_name != drug and e.adverse_event_term == event)
        
        # Count other drug-event combinations
        d = sum(1 for e in events if e.drug_name != drug and e.adverse_event_term != event)
        
        # Validate contingency table
        if a == 0:
            raise ValueError(f"No events found for {drug}-{event} combination")
        if b + c + d == 0:
            raise ValueError("Insufficient data for statistical analysis")
        
        # Use Code Interpreter for statistical calculations
        try:
            metrics = self._execute_statistical_analysis(a, b, c, d)
        except CodeInterpreterError as e:
            # Retry once on failure
            if self.config and self.config.code_interpreter.max_retries > 0:
                time.sleep(self.config.code_interpreter.retry_delay_seconds)
                try:
                    metrics = self._execute_statistical_analysis(a, b, c, d)
                except CodeInterpreterError:
                    raise CodeInterpreterError(
                        f"Code Interpreter failed after retry: {str(e)}"
                    )
            else:
                raise
        
        return metrics
    
    def _execute_statistical_analysis(
        self,
        a: int,
        b: int,
        c: int,
        d: int
    ) -> StatisticalMetrics:
        """
        Execute statistical analysis using Code Interpreter.
        
        This method would normally call the AgentCore Code Interpreter service.
        For now, it implements the calculations directly.
        
        Args:
            a, b, c, d: Contingency table values
            
        Returns:
            StatisticalMetrics
        """
        # If code_interpreter is provided (for testing), use it
        if self.code_interpreter:
            return self.code_interpreter.execute(a, b, c, d)
        
        # Otherwise, perform calculations directly
        # PRR = (a/b) / (c/d) = (a*d) / (b*c)
        if b == 0 or c == 0:
            prr = float('inf') if a > 0 else 0.0
        else:
            prr = (a * d) / (b * c) if (b * c) > 0 else 0.0
        
        # ROR = (a/c) / (b/d) = (a*d) / (b*c)
        if b == 0 or c == 0:
            ror = float('inf') if a > 0 else 0.0
        else:
            ror = (a * d) / (b * c) if (b * c) > 0 else 0.0
        
        # Calculate expected count
        total = a + b + c + d
        expected_count = ((a + b) * (a + c)) / total if total > 0 else 0.0
        
        # Calculate IC025 (simplified version)
        # IC = log2(observed/expected)
        # IC025 is the lower bound of 95% CI
        if expected_count > 0 and a > 0:
            ic = math.log2(a / expected_count)
            # Standard error for IC: SE = sqrt(1/a)
            se = math.sqrt(1/a)
            ic025 = ic - 1.96 * se
            ic975 = ic + 1.96 * se
        else:
            ic025 = -float('inf')
            ic975 = float('inf')
        
        return StatisticalMetrics(
            prr=prr,
            ror=ror,
            ic025=ic025,
            confidence_interval=(ic025, ic975),
            event_count=a,
            expected_count=expected_count
        )
    
    def _validate_events(self, events: List[AdverseEvent]) -> None:
        """
        Validate that all events have required fields.
        
        Args:
            events: List of adverse events
            
        Raises:
            ValueError: If any event is invalid
        """
        for i, event in enumerate(events):
            if not event.drug_name:
                raise ValueError(f"Event {i}: drug_name is required")
            if not event.adverse_event_term:
                raise ValueError(f"Event {i}: adverse_event_term is required")
            if not event.event_id:
                raise ValueError(f"Event {i}: event_id is required")
    
    def _group_events(
        self,
        events: List[AdverseEvent]
    ) -> Dict[Tuple[str, str], List[AdverseEvent]]:
        """
        Group events by drug-event combination.
        
        Args:
            events: List of adverse events
            
        Returns:
            Dictionary mapping (drug, event) tuples to lists of events
        """
        groups = {}
        for event in events:
            key = (event.drug_name, event.adverse_event_term)
            if key not in groups:
                groups[key] = []
            groups[key].append(event)
        return groups
    
    def _determine_severity(self, metrics: StatisticalMetrics) -> str:
        """
        Determine signal severity based on statistical metrics.
        
        Args:
            metrics: Statistical metrics
            
        Returns:
            Severity level: 'low', 'medium', 'high', or 'critical'
        """
        # Severity based on IC025 and event count
        if metrics.ic025 > 3.0 and metrics.event_count >= 10:
            return 'critical'
        elif metrics.ic025 > 2.0 and metrics.event_count >= 5:
            return 'high'
        elif metrics.ic025 > 1.0:
            return 'medium'
        else:
            return 'low'



def create_signal_detection_strands_agent(config=None):
    """
    Create a Strands Agent wrapper for Signal Detection Agent.
    
    This function creates a Strands Agent that can be used with A2AServer
    for agent-to-agent communication.
    
    Args:
        config: AgentCore configuration
        
    Returns:
        Strands Agent instance
    """
    from strands import Agent
    
    # Create the underlying agent
    agent_impl = SignalDetectionAgent(config=config)
    
    def analyze_events_tool(events_json: str) -> str:
        """
        Tool to analyze adverse events for signal detection.
        
        Args:
            events_json: JSON string containing list of adverse events
            
        Returns:
            JSON string with signal analysis results
        """
        import json
        
        try:
            # Parse events from JSON
            events_data = json.loads(events_json)
            events = [AdverseEvent(**e) for e in events_data]
            
            # Analyze events
            result = agent_impl.analyze_events(events)
            
            # Return as JSON
            return json.dumps({
                'signals': [s.__dict__ for s in result.signals],
                'total_events_analyzed': result.total_events_analyzed,
                'analysis_timestamp': result.analysis_timestamp.isoformat(),
                'errors': result.errors
            }, default=str)
            
        except Exception as e:
            return json.dumps({
                'error': str(e),
                'error_type': type(e).__name__
            })
    
    # Create Strands Agent
    return Agent(
        name="Signal Detection Agent",
        description="""
        I am a signal detection agent specialized in analyzing adverse event reports 
        using statistical methods. I calculate disproportionality metrics (PRR, ROR, IC025) 
        to identify potential safety signals that require investigation.
        """,
        tools=[analyze_events_tool],
        instructions="""
        When you receive adverse event data:
        1. Validate the data completeness
        2. Calculate statistical metrics (PRR, ROR, IC025) for each drug-event combination
        3. Flag signals where IC025 > 0 for investigation
        4. Return structured results with all metrics and confidence intervals
        5. Handle errors gracefully and provide descriptive error messages
        """
    )
