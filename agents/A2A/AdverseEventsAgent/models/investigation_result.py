"""InvestigationResult data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from .signal import Signal
from .literature import LiteratureResults
from .regulatory_report import RegulatoryReport


@dataclass
class InvestigationResult:
    """Represents the complete result of a signal investigation."""
    
    investigation_id: str
    status: str  # in_progress, completed, failed
    signal: Optional[Signal]
    literature: Optional[LiteratureResults]
    reports: List[RegulatoryReport]
    errors: List[str]
    started_at: datetime
    completed_at: Optional[datetime]
    
    def __post_init__(self):
        """Validate investigation result data."""
        if not self.investigation_id:
            raise ValueError("investigation_id is required")
        if self.status not in ['in_progress', 'completed', 'failed']:
            raise ValueError("status must be 'in_progress', 'completed', or 'failed'")
        if self.reports is None:
            self.reports = []
        if self.errors is None:
            self.errors = []
        
        # Validate status consistency
        if self.status == 'completed' and not self.completed_at:
            raise ValueError("completed_at is required when status is 'completed'")
