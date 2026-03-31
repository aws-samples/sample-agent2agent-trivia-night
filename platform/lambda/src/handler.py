"""
Lambda entry point for the LSS Workshop Platform Backend API.

Single handler with internal routing based on HTTP method and path.
Routes requests to the appropriate service and returns standardised
responses via the response utilities.
"""
import base64
import json
import traceback
import uuid
from typing import Any, Dict, Optional, Tuple

import boto3

from services.agent_service import AgentNotFoundError, AgentService
from services.search_service import SearchService
from services.health_service import HealthService
from services.chat_service import ChatService, ChatServiceError, AgentUnreachableError
from utils.response import build_success_response, build_error_response
from utils.validation import (
    validate_agent_card,
    validate_chat_request,
    validate_search_params,
    validate_agent_id,
    ValidationError,
)
from utils.logging import log_error, get_logger

# Module-level logger
logger = get_logger(__name__)

# Module-level singletons (reused across Lambda invocations)
agent_service = AgentService()
search_service = SearchService()
health_service = HealthService(agent_service=agent_service)
chat_service = ChatService(agent_service=agent_service)


def _parse_path(path: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Parse the request path into (base, agent_id, sub_resource).

    Examples::

        /agents            -> ("agents", None, None)
        /agents/search     -> ("agents_search", None, None)
        /agents/abc-123    -> ("agents", "abc-123", None)
        /agents/abc/health -> ("agents", "abc", "health")
        /chat              -> ("chat", None, None)

    Returns:
        A 3-tuple of (route_key, agent_id, sub_resource).
    """
    parts = [p for p in path.strip("/").split("/") if p]

    if not parts:
        return ("", None, None)

    if parts[0] == "chat":
        return ("chat", None, None)

    if parts[0] == "agents":
        if len(parts) == 1:
            return ("agents", None, None)
        if parts[1] == "search":
            return ("agents_search", None, None)
        if parts[1] == "sync-orchestrator":
            return ("agents_sync_orchestrator", None, None)
        agent_id = parts[1]
        sub_resource = parts[2] if len(parts) >= 3 else None
        return ("agents", agent_id, sub_resource)

    return ("", None, None)


def _parse_json_body(raw_body: Optional[str]) -> Dict[str, Any]:
    """Parse a JSON request body, raising ValidationError on failure."""
    if not raw_body:
        raise ValidationError(fields=["body"], message="Request body is required")
    try:
        data = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        raise ValidationError(fields=["body"], message="Invalid JSON in request body")
    return data


def _sync_orchestrator() -> Dict[str, Any]:
    """Find OrchestratorAgent in AgentCore Runtime and register/update it."""
    control = boto3.client("bedrock-agentcore-control")

    # Paginate through all runtimes
    orch = None
    kwargs = {}
    while True:
        resp = control.list_agent_runtimes(**kwargs)
        for rt in resp.get("agentRuntimes", []):
            if rt.get("agentRuntimeName", "").startswith("OrchestratorAgent_Agent"):
                orch = control.get_agent_runtime(agentRuntimeId=rt["agentRuntimeId"])
                break
        if orch or not resp.get("nextToken"):
            break
        kwargs["nextToken"] = resp["nextToken"]

    if not orch:
        return {"message": "OrchestratorAgent not found in AgentCore Runtime"}

    arn = orch["agentRuntimeArn"]
    name = orch["agentRuntimeName"]

    agent_card = {
        "name": "OrchestratorAgent",
        "description": "An orchestrator agent that coordinates multiple specialized agents to answer complex questions. It can delegate tasks to sub-agents like Calculator, Knowledge, and other agents.",
        "version": "1.0.0",
        "url": arn,
        "capabilities": {"streaming": True, "pushNotifications": False, "stateTransitionHistory": False},
        "authentication": {"schemes": ["Bearer"]},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {"id": "orchestration", "name": "orchestration", "description": "Coordinates multiple agents", "tags": ["orchestration"]},
            {"id": "multi-agent", "name": "multi-agent", "description": "Multi-agent collaboration", "tags": ["multi-agent"]},
            {"id": "coordination", "name": "coordination", "description": "Task coordination", "tags": ["coordination"]},
        ],
    }

    # Check if already registered, update if so
    existing = agent_service.list_agents(limit=100, offset=0)
    for a in existing.get("items", []):
        if a.get("name") == "OrchestratorAgent":
            agent_service.update_agent(a["agent_id"], agent_card)
            return {"message": f"OrchestratorAgent updated (id={a['agent_id']})", "agent_id": a["agent_id"], "arn": arn}

    agent_id = agent_service.create_agent(agent_card)
    return {"message": f"OrchestratorAgent registered (id={agent_id})", "agent_id": agent_id, "arn": arn}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler — routes API Gateway proxy events and Function URL events to services."""
    request_context = event.get("requestContext", {})

    # Detect Function URL events (have requestContext.http instead of httpMethod)
    if "http" in request_context:
        return _handle_function_url_event(event, context)

    return _handle_api_gateway_event(event, context)


def _handle_function_url_event(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle Lambda Function URL events — only supports POST /chat."""
    request_id = event.get("requestContext", {}).get("requestId", str(uuid.uuid4()))
    http = event["requestContext"]["http"]
    method = http.get("method", "")
    path = http.get("path", "")

    logger.info(f"FunctionURL Request {request_id}: {method} {path}")

    try:
        if method == "OPTIONS":
            return _furl_response(200, {}, request_id)

        if method != "POST":
            return _furl_response(405, {"error_code": "METHOD_NOT_ALLOWED", "message": "Only POST is supported"}, request_id)

        body = event.get("body", "")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")

        data = _parse_json_body(body)
        validate_chat_request(data)
        result = chat_service.invoke_agent(
            agent_id=data["agentId"], message=data["message"]
        )
        return _furl_response(200, result, request_id)

    except ValidationError as exc:
        log_error(logger, request_id, "VALIDATION_ERROR", exc.message,
                  traceback.format_exc(), path, method)
        return _furl_response(400, {"error_code": "VALIDATION_ERROR", "message": exc.message, "details": {"fields": exc.fields}}, request_id)
    except AgentNotFoundError as exc:
        log_error(logger, request_id, "NOT_FOUND", exc.message,
                  traceback.format_exc(), path, method)
        return _furl_response(404, {"error_code": "NOT_FOUND", "message": exc.message}, request_id)
    except (ChatServiceError, AgentUnreachableError) as exc:
        log_error(logger, request_id, exc.error_code, exc.message,
                  traceback.format_exc(), path, method)
        return _furl_response(502, {"error_code": exc.error_code, "message": exc.message, "details": exc.details}, request_id)
    except Exception as exc:
        log_error(logger, request_id, "INTERNAL_ERROR", str(exc),
                  traceback.format_exc(), path, method)
        return _furl_response(500, {"error_code": "INTERNAL_ERROR", "message": "Internal server error"}, request_id)


def _furl_response(status_code: int, body: Any, request_id: str) -> Dict[str, Any]:
    """Build a Function URL response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        },
        "body": json.dumps(body),
    }


def _handle_api_gateway_event(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle API Gateway proxy integration events."""
    request_id = event.get("requestContext", {}).get("requestId", str(uuid.uuid4()))
    method = event.get("httpMethod", "")
    path = event.get("path", "")

    logger.info(f"Request {request_id}: {method} {path}")

    try:
        # CORS preflight
        if method == "OPTIONS":
            return build_success_response({}, request_id=request_id)

        query_params = event.get("queryStringParameters") or {}
        body = event.get("body")
        route_key, agent_id, sub_resource = _parse_path(path)

        # ---- /agents (collection) ----
        if route_key == "agents" and agent_id is None:
            if method == "POST":
                data = _parse_json_body(body)
                validate_agent_card(data)
                new_id = agent_service.create_agent(data)
                return build_success_response(
                    {"agent_id": new_id, "message": "Agent created successfully"},
                    status_code=201,
                    request_id=request_id,
                )
            if method == "GET":
                limit = int(query_params.get("limit", 50))
                offset = int(query_params.get("offset", 0))
                result = agent_service.list_agents(limit=limit, offset=offset)
                return build_success_response(result, request_id=request_id)

        # ---- /agents/search ----
        elif route_key == "agents_search":
            if method == "GET":
                validate_search_params(query_params)
                query_text = query_params.get("query")
                skills_raw = query_params.get("skills")
                skills = (
                    [s.strip() for s in skills_raw.split(",") if s.strip()]
                    if skills_raw
                    else None
                )
                result = search_service.search_agents(
                    query=query_text, skills=skills
                )
                return build_success_response(result, request_id=request_id)

        # ---- /agents/sync-orchestrator ----
        elif route_key == "agents_sync_orchestrator":
            if method == "POST":
                result = _sync_orchestrator()
                return build_success_response(result, request_id=request_id)

        # ---- /agents/{agentId}/health ----
        elif route_key == "agents" and agent_id is not None and sub_resource == "health":
            validate_agent_id(agent_id)
            if method == "POST":
                result = health_service.update_health(agent_id)
                return build_success_response(result, request_id=request_id)

        # ---- /agents/{agentId} ----
        elif route_key == "agents" and agent_id is not None and sub_resource is None:
            validate_agent_id(agent_id)
            if method == "GET":
                agent = agent_service.get_agent(agent_id)
                return build_success_response(agent, request_id=request_id)
            if method == "PUT":
                data = _parse_json_body(body)
                validate_agent_card(data)
                agent_service.update_agent(agent_id, data)
                return build_success_response(
                    {"agent_id": agent_id, "message": "Agent updated successfully"},
                    request_id=request_id,
                )
            if method == "DELETE":
                agent_service.delete_agent(agent_id)
                return build_success_response(
                    {"agent_id": agent_id, "message": "Agent deleted successfully"},
                    request_id=request_id,
                )

        # ---- /chat ---- (Moved this method to use function URL to avoid the API Gateway of 29s)
        # elif route_key == "chat": 
        #     if method == "POST":
        #         data = _parse_json_body(body)
        #         validate_chat_request(data)
        #         result = chat_service.invoke_agent(
        #             agent_id=data["agentId"], message=data["message"]
        #         )
        #         return build_success_response(result, request_id=request_id)

        # ---- No matching route ----
        return build_error_response(
            status_code=404,
            message=f"No route found for {method} {path}",
            request_id=request_id,
        )

    except ValidationError as exc:
        log_error(logger, request_id, "VALIDATION_ERROR", exc.message,
                  traceback.format_exc(), path, method)
        return build_error_response(
            status_code=400,
            message=exc.message,
            details={"fields": exc.fields},
            request_id=request_id,
        )
    except AgentNotFoundError as exc:
        log_error(logger, request_id, "NOT_FOUND", exc.message,
                  traceback.format_exc(), path, method)
        return build_error_response(
            status_code=404,
            message=exc.message,
            request_id=request_id,
        )
    except (ChatServiceError, AgentUnreachableError) as exc:
        log_error(logger, request_id, exc.error_code, exc.message,
                  traceback.format_exc(), path, method)
        return build_error_response(
            status_code=502,
            message=exc.message,
            details=exc.details,
            request_id=request_id,
        )
    except Exception as exc:
        log_error(logger, request_id, "INTERNAL_ERROR", str(exc),
                  traceback.format_exc(), path, method)
        return build_error_response(
            status_code=500,
            message="Internal server error",
            request_id=request_id,
        )
