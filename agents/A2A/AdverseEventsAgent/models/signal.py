"""Signal data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass
class Signal:
    """Represents a detected safety signal."""
    
    signal_id: str
    drug_name: str
    adverse_event_term: str
    event_count: int
    expected_count: float
    prr: float  # Proportional Reporting Ratio
    ror: float  # Reporting Odds Ratio
    ic025: float  # Information Component lower bound
    confidence_interval: Tuple[float, float]
    detected_at: datetime
    severity: str  # low, medium, high, critical
    
    def __post_init__(self):
        """Validate signal data."""
        if not self.signal_id:
            raise ValueError("signal_id is required")
        if not self.drug_name:
            raise ValueError("drug_name is required")
        if not self.adverse_event_term:
            raise ValueError("adverse_event_term is required")
        if self.event_count < 0:
            raise ValueError("event_count must be non-negative")
        if self.expected_count < 0:
            raise ValueError("expected_count must be non-negative")
        if self.severity not in ['low', 'medium', 'high', 'critical']:
            raise ValueError("severity must be 'low', 'medium', 'high', or 'critical'")
    
    def is_flagged(self) -> bool:
        """Check if signal should be flagged for investigation (IC025 > 0)."""
        return self.ic025 > 0
