"""AdverseEvent data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AdverseEvent:
    """Represents an adverse event report."""
    
    event_id: str
    drug_name: str
    adverse_event_term: str
    medra_code: str
    patient_age: Optional[int]
    patient_sex: Optional[str]
    event_date: datetime
    outcome: str  # recovered, fatal, hospitalization, etc.
    reporter_type: str  # physician, pharmacist, consumer
    
    def __post_init__(self):
        """Validate adverse event data."""
        if not self.event_id:
            raise ValueError("event_id is required")
        if not self.drug_name:
            raise ValueError("drug_name is required")
        if not self.adverse_event_term:
            raise ValueError("adverse_event_term is required")
        if not self.medra_code:
            raise ValueError("medra_code is required")
        if self.patient_sex and self.patient_sex not in ['M', 'F', 'U']:
            raise ValueError("patient_sex must be 'M', 'F', or 'U'")
        if not self.outcome:
            raise ValueError("outcome is required")
        if not self.reporter_type:
            raise ValueError("reporter_type is required")
