"""
Request validation utilities for the Backend API.

Each validation function returns ``None`` on success and raises
:class:`ValidationError` with a descriptive message when the input is
invalid.  The exception carries the field names that failed validation so
callers can build structured error responses.
"""
from typing import Any, Dict, List, Optional


class ValidationError(Exception):
    """Raised when request data fails validation.

    Attributes:
        fields: List of field names that failed validation.
        message: Human-readable description of the failure.
    """

    def __init__(self, fields: List[str], message: str) -> None:
        self.fields = fields
        self.message = message
        super().__init__(message)


def validate_agent_card(body: Any) -> None:
    """Validate an agent card creation/update payload.

    Requires ``name``, ``description``, and ``url`` to be present and
    non-empty strings.

    Args:
        body: Parsed JSON body from the request.

    Raises:
        ValidationError: If *body* is not a dict or required fields are
            missing / empty.
    """
    if not isinstance(body, dict):
        raise ValidationError(
            fields=["body"],
            message="Request body must be a JSON object",
        )

    required_fields = ["name", "description", "url"]
    missing: List[str] = []

    for field in required_fields:
        value = body.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)

    if missing:
        raise ValidationError(
            fields=missing,
            message=f"Missing or empty required fields: {', '.join(missing)}",
        )


def validate_chat_request(body: Any) -> None:
    """Validate a ``POST /chat`` request payload.

    Requires ``agentId`` and ``message`` to be non-empty strings.

    Args:
        body: Parsed JSON body from the request.

    Raises:
        ValidationError: If required fields are missing or empty.
    """
    if not isinstance(body, dict):
        raise ValidationError(
            fields=["body"],
            message="Request body must be a JSON object",
        )

    missing: List[str] = []

    agent_id = body.get("agentId")
    if not isinstance(agent_id, str) or not agent_id.strip():
        missing.append("agentId")

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        missing.append("message")

    if missing:
        raise ValidationError(
            fields=missing,
            message=f"Missing or empty required fields: {', '.join(missing)}",
        )


def validate_search_params(params: Dict[str, Any]) -> None:
    """Validate search query parameters.

    At least one of ``query`` or ``skills`` must be provided and non-empty.

    Args:
        params: Query-string parameters dict.

    Raises:
        ValidationError: If neither ``query`` nor ``skills`` is supplied.
    """
    has_query = False
    has_skills = False

    query = params.get("query")
    if isinstance(query, str) and query.strip():
        has_query = True

    skills = params.get("skills")
    if isinstance(skills, str) and skills.strip():
        has_skills = True
    elif isinstance(skills, list) and len(skills) > 0:
        has_skills = True

    if not has_query and not has_skills:
        raise ValidationError(
            fields=["query", "skills"],
            message="At least one of 'query' or 'skills' must be provided",
        )


def validate_agent_id(agent_id: Any) -> None:
    """Validate an ``agentId`` path parameter.

    Must be a non-empty string that is not purely whitespace.

    Args:
        agent_id: The raw path parameter value.

    Raises:
        ValidationError: If *agent_id* is empty or whitespace-only.
    """
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValidationError(
            fields=["agentId"],
            message="agentId must be a non-empty, non-whitespace string",
        )
