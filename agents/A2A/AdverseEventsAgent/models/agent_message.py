"""AgentMessage data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class AgentMessage:
    """Represents a message exchanged between agents."""
    
    message_id: str
    message_type: str
    sender_agent_id: str
    recipient_agent_id: Optional[str]
    timestamp: datetime
    payload: Dict[str, Any]
    correlation_id: str  # Links messages in same investigation
    
    def __post_init__(self):
        """Validate agent message data."""
        if not self.message_id:
            raise ValueError("message_id is required")
        if not self.message_type:
            raise ValueError("message_type is required")
        if not self.sender_agent_id:
            raise ValueError("sender_agent_id is required")
        if not self.correlation_id:
            raise ValueError("correlation_id is required")
        if self.payload is None:
            raise ValueError("payload is required")
        
        # Validate message_type
        valid_types = ['signal_detected', 'literature_request', 'report_request', 
                      'signal_analysis_result', 'literature_result', 'report_result',
                      'error', 'status_update']
        if self.message_type not in valid_types:
            raise ValueError(f"message_type must be one of {valid_types}")
