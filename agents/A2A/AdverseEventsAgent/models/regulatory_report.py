"""RegulatoryReport data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import List

from .signal import Signal
from .literature import Article


@dataclass
class RegulatoryReport:
    """Represents a regulatory report for FDA or EMA submission."""
    
    report_id: str
    report_type: str  # medwatch, eudravigilance
    signal: Signal
    literature_references: List[Article]
    clinical_assessment: str
    generated_at: datetime
    validated: bool
    submission_status: str  # draft, submitted, accepted
    
    def __post_init__(self):
        """Validate regulatory report data."""
        if not self.report_id:
            raise ValueError("report_id is required")
        if self.report_type not in ['medwatch', 'eudravigilance']:
            raise ValueError("report_type must be 'medwatch' or 'eudravigilance'")
        if not self.signal:
            raise ValueError("signal is required")
        if not self.clinical_assessment:
            raise ValueError("clinical_assessment is required")
        if self.submission_status not in ['draft', 'submitted', 'accepted']:
            raise ValueError("submission_status must be 'draft', 'submitted', or 'accepted'")
