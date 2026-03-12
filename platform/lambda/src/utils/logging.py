"""
Structured logging utilities for the Backend API.

Provides a configured logger factory and a structured error logging helper
that outputs JSON-formatted error context for consistent log parsing in
CloudWatch.
"""
import json
import logging
from typing import Any, Dict, Optional


def get_logger(name: str) -> logging.Logger:
    """Return a configured :class:`logging.Logger` for the given module name.

    The logger is set to ``INFO`` level.  A :class:`logging.StreamHandler` with
    a simple ``%(asctime)s - %(name)s - %(levelname)s - %(message)s`` format is
    attached only if the logger has no handlers yet (avoids duplicate output
    when called multiple times for the same *name*).

    Args:
        name: Logger name — typically ``__name__`` of the calling module.

    Returns:
        A ready-to-use :class:`logging.Logger`.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def log_error(
    logger: logging.Logger,
    request_id: str,
    error_code: str,
    message: str,
    stack_trace: str,
    path: str,
    method: str,
) -> None:
    """Log a structured error entry at ``ERROR`` level.

    The error context is serialised as a JSON string so that CloudWatch and
    other log aggregators can parse it reliably.

    Args:
        logger: The logger instance to write to.
        request_id: Correlation ID for the current request.
        error_code: Application error code (e.g. ``VALIDATION_ERROR``).
        message: Human-readable error description.
        stack_trace: Full Python traceback string.
        path: Request path (e.g. ``/agents``).
        method: HTTP method (e.g. ``POST``).
    """
    error_context: Dict[str, Any] = {
        "request_id": request_id,
        "error_code": error_code,
        "message": message,
        "stack_trace": stack_trace,
        "path": path,
        "method": method,
    }
    logger.error(json.dumps(error_context))
