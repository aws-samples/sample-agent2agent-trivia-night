"""
Communication Audit Logger for Agent-to-Agent Communication.

This module implements audit logging for all inter-agent messages
to satisfy compliance and traceability requirements.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from models.agent_message import AgentMessage


# Configure logging
logger = logging.getLogger(__name__)


class CommunicationAuditLogger:
    """
    Audit logger for agent-to-agent communication.
    
    Logs all inter-agent messages with timestamp, sender, recipient,
    and message type for audit and compliance purposes.
    """
    
    def __init__(self, log_file: Optional[str] = None):
        """
        Initialize Communication Audit Logger.
        
        Args:
            log_file: Optional path to audit log file. If not provided,
                     logs to default location: logs/communication_audit.log
        """
        if log_file is None:
            log_file = "logs/communication_audit.log"
        
        self.log_file = Path(log_file)
        
        # Create logs directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure file handler for audit logs
        self.file_handler = logging.FileHandler(self.log_file)
        self.file_handler.setLevel(logging.INFO)
        
        # Use JSON format for structured logging
        formatter = logging.Formatter(
            '%(message)s'  # We'll format as JSON ourselves
        )
        self.file_handler.setFormatter(formatter)
        
        # Create dedicated audit logger
        self.audit_logger = logging.getLogger('communication_audit')
        self.audit_logger.setLevel(logging.INFO)
        self.audit_logger.addHandler(self.file_handler)
        
        # Prevent propagation to root logger
        self.audit_logger.propagate = False
    
    def log_message(
        self,
        message: AgentMessage,
        direction: str = 'sent',
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an agent message to the audit log.
        
        Args:
            message: AgentMessage to log
            direction: Direction of message ('sent' or 'received')
            additional_context: Optional additional context to include in log
        """
        # Create audit log entry
        log_entry = {
            'audit_timestamp': datetime.now().isoformat(),
            'direction': direction,
            'message_id': message.message_id,
            'message_type': message.message_type,
            'sender_agent_id': message.sender_agent_id,
            'recipient_agent_id': message.recipient_agent_id,
            'message_timestamp': message.timestamp.isoformat(),
            'correlation_id': message.correlation_id,
            'payload_summary': self._summarize_payload(message.payload)
        }
        
        # Add additional context if provided
        if additional_context:
            log_entry['context'] = additional_context
        
        # Log as JSON
        self.audit_logger.info(json.dumps(log_entry))
    
    def log_message_sent(
        self,
        message: AgentMessage,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a message that was sent.
        
        Args:
            message: AgentMessage that was sent
            additional_context: Optional additional context
        """
        self.log_message(message, direction='sent', additional_context=additional_context)
    
    def log_message_received(
        self,
        message: AgentMessage,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a message that was received.
        
        Args:
            message: AgentMessage that was received
            additional_context: Optional additional context
        """
        self.log_message(message, direction='received', additional_context=additional_context)
    
    def log_error(
        self,
        error: Exception,
        message: Optional[AgentMessage] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a communication error.
        
        Args:
            error: Exception that occurred
            message: Optional message that caused the error
            additional_context: Optional additional context
        """
        log_entry = {
            'audit_timestamp': datetime.now().isoformat(),
            'event_type': 'error',
            'error_type': type(error).__name__,
            'error_message': str(error)
        }
        
        if message:
            log_entry['message_id'] = message.message_id
            log_entry['correlation_id'] = message.correlation_id
        
        if additional_context:
            log_entry['context'] = additional_context
        
        self.audit_logger.error(json.dumps(log_entry))
    
    def _summarize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a summary of the payload for logging.
        
        Avoids logging large payloads in full to keep audit logs manageable.
        
        Args:
            payload: Message payload
            
        Returns:
            Summarized payload
        """
        summary = {}
        
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)):
                # Include simple types directly
                if isinstance(value, str) and len(value) > 100:
                    summary[key] = f"{value[:100]}... (truncated)"
                else:
                    summary[key] = value
            elif isinstance(value, list):
                summary[key] = f"<list with {len(value)} items>"
            elif isinstance(value, dict):
                summary[key] = f"<dict with {len(value)} keys>"
            else:
                summary[key] = f"<{type(value).__name__}>"
        
        return summary
    
    def get_audit_log_path(self) -> str:
        """
        Get the path to the audit log file.
        
        Returns:
            Path to audit log file
        """
        return str(self.log_file)
    
    def query_logs(
        self,
        correlation_id: Optional[str] = None,
        sender_agent_id: Optional[str] = None,
        recipient_agent_id: Optional[str] = None,
        message_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> list:
        """
        Query audit logs with filters.
        
        Args:
            correlation_id: Filter by correlation ID
            sender_agent_id: Filter by sender agent ID
            recipient_agent_id: Filter by recipient agent ID
            message_type: Filter by message type
            start_time: Filter by start time
            end_time: Filter by end time
            
        Returns:
            List of matching log entries
        """
        matching_entries = []
        
        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        
                        # Apply filters
                        if correlation_id and entry.get('correlation_id') != correlation_id:
                            continue
                        if sender_agent_id and entry.get('sender_agent_id') != sender_agent_id:
                            continue
                        if recipient_agent_id and entry.get('recipient_agent_id') != recipient_agent_id:
                            continue
                        if message_type and entry.get('message_type') != message_type:
                            continue
                        
                        # Time filters
                        if start_time or end_time:
                            entry_time = datetime.fromisoformat(entry.get('audit_timestamp', ''))
                            if start_time and entry_time < start_time:
                                continue
                            if end_time and entry_time > end_time:
                                continue
                        
                        matching_entries.append(entry)
                        
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
        
        except FileNotFoundError:
            logger.warning(f"Audit log file not found: {self.log_file}")
        
        return matching_entries


# Global audit logger instance
_audit_logger: Optional[CommunicationAuditLogger] = None


def get_audit_logger(log_file: Optional[str] = None) -> CommunicationAuditLogger:
    """
    Get the global audit logger instance.
    
    Args:
        log_file: Optional path to audit log file
        
    Returns:
        CommunicationAuditLogger instance
    """
    global _audit_logger
    
    if _audit_logger is None:
        _audit_logger = CommunicationAuditLogger(log_file=log_file)
    
    return _audit_logger


# Convenience functions
def log_message_sent(message: AgentMessage, context: Optional[Dict[str, Any]] = None) -> None:
    """Log a message that was sent."""
    get_audit_logger().log_message_sent(message, additional_context=context)


def log_message_received(message: AgentMessage, context: Optional[Dict[str, Any]] = None) -> None:
    """Log a message that was received."""
    get_audit_logger().log_message_received(message, additional_context=context)


def log_communication_error(
    error: Exception,
    message: Optional[AgentMessage] = None,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """Log a communication error."""
    get_audit_logger().log_error(error, message=message, additional_context=context)
