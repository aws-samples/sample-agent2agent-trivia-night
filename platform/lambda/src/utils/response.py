"""
Response formatting utilities for the Backend API.

Provides standardized success and error response builders with CORS headers
for API Gateway Lambda proxy integration.
"""
import json
from typing import Any, Dict, Optional


# CORS headers included in all responses
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type, X-Amz-Date, Authorization, X-Api-Key, "
        "X-Amz-Security-Token, X-Amz-User-Agent, X-Amz-Content-Sha256, X-Amz-Target"
    ),
}

# Error code mapping: HTTP status code → application error code
ERROR_CODE_MAP: Dict[int, str] = {
    400: "VALIDATION_ERROR",
    404: "NOT_FOUND",
    502: "AGENT_UNREACHABLE",
    500: "INTERNAL_ERROR",
}


def build_success_response(
    body: Any, status_code: int = 200, request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a success response in API Gateway Lambda proxy format.

    Args:
        body: Response payload (will be JSON-serialised).
        status_code: HTTP status code (default 200).
        request_id: Optional request ID for the X-Request-ID header.

    Returns:
        API Gateway proxy-compatible response dict.
    """
    headers = {**CORS_HEADERS}
    if request_id:
        headers["X-Request-ID"] = request_id

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }


def build_error_response(
    status_code: int,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a standardised error response with CORS headers.

    The error body follows the format:
        { "error_code": "<CODE>", "message": "<description>", "details": {} }

    If *error_code* is not supplied it is derived from *status_code* via
    ``ERROR_CODE_MAP``.  Unknown status codes fall back to ``INTERNAL_ERROR``.

    Args:
        status_code: HTTP status code (400, 404, 500, 502, …).
        message: Human-readable error description.
        details: Optional dict with additional context.
        request_id: Optional request ID for the X-Request-ID header.
        error_code: Explicit error code; overrides the automatic mapping.

    Returns:
        API Gateway proxy-compatible error response dict.
    """
    resolved_code = error_code or ERROR_CODE_MAP.get(status_code, "INTERNAL_ERROR")

    error_body: Dict[str, Any] = {
        "error_code": resolved_code,
        "message": message,
        "details": details or {},
    }

    headers = {**CORS_HEADERS}
    if request_id:
        headers["X-Request-ID"] = request_id

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(error_body),
    }
