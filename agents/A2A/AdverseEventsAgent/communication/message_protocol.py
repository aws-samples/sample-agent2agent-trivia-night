"""
Message Protocol for Agent-to-Agent Communication.

This module implements message validation, serialization, and utilities
for A2A communication using the Strands framework.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import asdict

from models.agent_message import AgentMessage


# Configure logging
logger = logging.getLogger(__name__)


class MessageValidationError(Exception):
    """Exception raised when message validation fails."""
    pass


class MessageProtocol:
    """
    Protocol handler for agent-to-agent communication.
    
    Provides message validation, serialization, and deserialization
    utilities for the Strands A2A framework.
    """
    
    @staticmethod
    def validate_message(message: AgentMessage) -> bool:
        """
        Validate an AgentMessage against the schema.
        
        Args:
            message: AgentMessage to validate
            
        Returns:
            True if valid
            
        Raises:
            MessageValidationError: If message is invalid
        """
        try:
            # Check required fields
            if not message.message_id:
                raise MessageValidationError("message_id is required")
            
            if not message.message_type:
                raise MessageValidationError("message_type is required")
            
            if not message.sender_agent_id:
                raise MessageValidationError("sender_agent_id is required")
            
            if not message.correlation_id:
                raise MessageValidationError("correlation_id is required")
            
            if message.payload is None:
                raise MessageValidationError("payload is required")
            
            # Validate message_type
            valid_types = [
                'signal_detected', 'literature_request', 'report_request',
                'signal_analysis_result', 'literature_result', 'report_result',
                'error', 'status_update'
            ]
            if message.message_type not in valid_types:
                raise MessageValidationError(
                    f"Invalid message_type: {message.message_type}. "
                    f"Must be one of {valid_types}"
                )
            
            # Validate timestamp
            if not isinstance(message.timestamp, datetime):
                raise MessageValidationError("timestamp must be a datetime object")
            
            # Validate payload is a dictionary
            if not isinstance(message.payload, dict):
                raise MessageValidationError("payload must be a dictionary")
            
            return True
            
        except AttributeError as e:
            raise MessageValidationError(f"Missing required attribute: {str(e)}")
    
    @staticmethod
    def serialize_message(message: AgentMessage) -> str:
        """
        Serialize an AgentMessage to JSON string.
        
        Args:
            message: AgentMessage to serialize
            
        Returns:
            JSON string representation
            
        Raises:
            MessageValidationError: If message is invalid
        """
        # Validate before serialization
        MessageProtocol.validate_message(message)
        
        try:
            # Convert to dictionary
            message_dict = asdict(message)
            
            # Convert datetime to ISO format string
            if isinstance(message_dict['timestamp'], datetime):
                message_dict['timestamp'] = message_dict['timestamp'].isoformat()
            
            # Serialize to JSON
            return json.dumps(message_dict, default=str)
            
        except Exception as e:
            raise MessageValidationError(f"Serialization failed: {str(e)}")
    
    @staticmethod
    def deserialize_message(message_json: str) -> AgentMessage:
        """
        Deserialize a JSON string to AgentMessage.
        
        Args:
            message_json: JSON string to deserialize
            
        Returns:
            AgentMessage instance
            
        Raises:
            MessageValidationError: If deserialization fails
        """
        try:
            # Parse JSON
            message_dict = json.loads(message_json)
            
            # Convert timestamp string to datetime
            if isinstance(message_dict.get('timestamp'), str):
                message_dict['timestamp'] = datetime.fromisoformat(
                    message_dict['timestamp']
                )
            
            # Create AgentMessage instance
            message = AgentMessage(**message_dict)
            
            # Validate
            MessageProtocol.validate_message(message)
            
            return message
            
        except json.JSONDecodeError as e:
            raise MessageValidationError(f"Invalid JSON: {str(e)}")
        except TypeError as e:
            raise MessageValidationError(f"Invalid message structure: {str(e)}")
        except Exception as e:
            raise MessageValidationError(f"Deserialization failed: {str(e)}")
    
    @staticmethod
    def create_error_message(
        error: Exception,
        sender_agent_id: str,
        correlation_id: str,
        recipient_agent_id: Optional[str] = None
    ) -> AgentMessage:
        """
        Create an error message from an exception.
        
        Args:
            error: Exception that occurred
            sender_agent_id: ID of agent sending error
            correlation_id: Correlation ID for investigation
            recipient_agent_id: Optional recipient agent ID
            
        Returns:
            AgentMessage with error details
        """
        import uuid
        
        return AgentMessage(
            message_id=str(uuid.uuid4()),
            message_type='error',
            sender_agent_id=sender_agent_id,
            recipient_agent_id=recipient_agent_id,
            timestamp=datetime.now(),
            payload={
                'error_type': type(error).__name__,
                'error_message': str(error),
                'error_details': getattr(error, '__dict__', {})
            },
            correlation_id=correlation_id
        )
    
    @staticmethod
    def validate_message_dict(message_dict: Dict[str, Any]) -> bool:
        """
        Validate a message dictionary before creating AgentMessage.
        
        Args:
            message_dict: Dictionary to validate
            
        Returns:
            True if valid
            
        Raises:
            MessageValidationError: If invalid
        """
        required_fields = [
            'message_id', 'message_type', 'sender_agent_id',
            'timestamp', 'payload', 'correlation_id'
        ]
        
        for field in required_fields:
            if field not in message_dict:
                raise MessageValidationError(f"Missing required field: {field}")
        
        return True


class MessageSerializer:
    """
    Utility class for message serialization/deserialization.
    
    Provides convenience methods for working with messages in different formats.
    """
    
    @staticmethod
    def to_json(message: AgentMessage) -> str:
        """Serialize message to JSON."""
        return MessageProtocol.serialize_message(message)
    
    @staticmethod
    def from_json(message_json: str) -> AgentMessage:
        """Deserialize message from JSON."""
        return MessageProtocol.deserialize_message(message_json)
    
    @staticmethod
    def to_dict(message: AgentMessage) -> Dict[str, Any]:
        """Convert message to dictionary."""
        message_dict = asdict(message)
        # Convert datetime to ISO format
        if isinstance(message_dict['timestamp'], datetime):
            message_dict['timestamp'] = message_dict['timestamp'].isoformat()
        return message_dict
    
    @staticmethod
    def from_dict(message_dict: Dict[str, Any]) -> AgentMessage:
        """Create message from dictionary."""
        # Validate first
        MessageProtocol.validate_message_dict(message_dict)
        
        # Convert timestamp if needed
        if isinstance(message_dict.get('timestamp'), str):
            message_dict['timestamp'] = datetime.fromisoformat(
                message_dict['timestamp']
            )
        
        return AgentMessage(**message_dict)
    
    @staticmethod
    def batch_serialize(messages: List[AgentMessage]) -> str:
        """Serialize multiple messages to JSON array."""
        return json.dumps(
            [MessageSerializer.to_dict(msg) for msg in messages],
            default=str
        )
    
    @staticmethod
    def batch_deserialize(messages_json: str) -> List[AgentMessage]:
        """Deserialize JSON array to list of messages."""
        messages_list = json.loads(messages_json)
        return [MessageSerializer.from_dict(msg_dict) for msg_dict in messages_list]


# Convenience functions
def validate_message(message: AgentMessage) -> bool:
    """Validate an AgentMessage."""
    return MessageProtocol.validate_message(message)


def serialize_message(message: AgentMessage) -> str:
    """Serialize an AgentMessage to JSON."""
    return MessageProtocol.serialize_message(message)


def deserialize_message(message_json: str) -> AgentMessage:
    """Deserialize JSON to AgentMessage."""
    return MessageProtocol.deserialize_message(message_json)


def create_error_message(
    error: Exception,
    sender_agent_id: str,
    correlation_id: str,
    recipient_agent_id: Optional[str] = None
) -> AgentMessage:
    """Create an error message from an exception."""
    return MessageProtocol.create_error_message(
        error, sender_agent_id, correlation_id, recipient_agent_id
    )
