"""
Chat service for invoking registered agents.

Uses the boto3 bedrock-agentcore client's invoke_agent_runtime API
to communicate with agents deployed on AgentCore Runtime.
"""
import json
import os
import uuid
from typing import Any, Dict, Optional

import boto3

from services.agent_service import AgentNotFoundError, AgentService
from utils.logging import get_logger

logger = get_logger(__name__)


class ChatServiceError(Exception):
    """Base error for chat service failures (maps to 502)."""
    def __init__(self, message: str, error_code: str = "AGENT_UNREACHABLE",
                 details: Optional[Dict[str, Any]] = None) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class AgentUnreachableError(ChatServiceError):
    """Raised when the agent cannot be reached or times out."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "AGENT_UNREACHABLE", details)


class ChatService:
    """Invokes registered agents via AgentCore Runtime API."""

    INVOCATION_TIMEOUT = 25

    def __init__(self, agent_service: Optional[AgentService] = None) -> None:
        self.agent_service = agent_service or AgentService()
        self._default_region = os.environ.get("AWS_REGION", "us-east-1")
        self._agentcore_clients: dict = {}
        logger.info("Initialised ChatService")

    def _get_agentcore_client(self, region: str):
        """Get or create a bedrock-agentcore client for the given region."""
        if region not in self._agentcore_clients:
            self._agentcore_clients[region] = boto3.client(
                "bedrock-agentcore", region_name=region
            )
        return self._agentcore_clients[region]

    def _region_from_arn(self, arn: str) -> str:
        """Extract region from an ARN like arn:aws:bedrock-agentcore:us-east-1:..."""
        parts = arn.split(":")
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        return self._default_region

    def _extract_arn_from_url(self, url: str) -> Optional[str]:
        """Extract the AgentCore Runtime ARN from a registered URL.

        URLs registered by our scripts look like:
        https://bedrock-agentcore.us-east-1.amazonaws.com/runtime/<id>/runtime-endpoint/DEFAULT

        The ARN is: arn:aws:bedrock-agentcore:<region>:<account>:runtime/<id>
        """
        if "bedrock-agentcore" not in url:
            return None

        # Try to extract runtime ID from URL path
        parts = url.rstrip("/").split("/")
        try:
            runtime_idx = parts.index("runtime")
            runtime_id = parts[runtime_idx + 1]
        except (ValueError, IndexError):
            return None

        # Get region from URL hostname
        # e.g. bedrock-agentcore.us-east-1.amazonaws.com
        try:
            hostname = url.split("//")[1].split("/")[0]
            region = hostname.split(".")[1]
        except (IndexError, AttributeError):
            region = os.environ.get("AWS_REGION", "us-east-1")

        # Get account ID from STS
        try:
            sts = boto3.client("sts")
            account_id = sts.get_caller_identity()["Account"]
        except Exception:
            account_id = "unknown"

        return f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/{runtime_id}"

    def invoke_agent(self, agent_id: str, message: str) -> Dict[str, Any]:
        """Look up an agent and invoke it via AgentCore Runtime API."""
        logger.info(f"Invoking agent agent_id={agent_id}")

        agent = self.agent_service.get_agent(agent_id)
        agent_url = agent.get("url", "")
        agent_name = agent.get("name", "Unknown Agent")

        if not agent_url:
            raise AgentUnreachableError("Agent has no registered URL", {"agent_id": agent_id})

        logger.info(f"Agent URL/ARN: {agent_url}")

        # If the url field is already an ARN, use it directly
        if agent_url.startswith("arn:aws:bedrock-agentcore:"):
            agent_arn = agent_url
        else:
            agent_arn = self._extract_arn_from_url(agent_url)

        if not agent_arn:
            raise AgentUnreachableError(
                "Could not determine AgentCore Runtime ARN from agent URL",
                {"agent_id": agent_id, "agent_url": agent_url},
            )

        logger.info(f"Using AgentCore ARN: {agent_arn}")

        # Use a client in the same region as the agent
        agent_region = self._region_from_arn(agent_arn)
        client = self._get_agentcore_client(agent_region)
        logger.info(f"Using AgentCore region: {agent_region}")

        try:
            payload = json.dumps({"prompt": message}).encode()
            session_id = str(uuid.uuid4())

            response = client.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                runtimeSessionId=session_id,
                payload=payload,
            )

            # Read the response blob
            raw_response = response.get("response")
            if hasattr(raw_response, "read"):
                # StreamingBody — read all bytes
                response_bytes = raw_response.read()
            elif isinstance(raw_response, bytes):
                response_bytes = raw_response
            else:
                response_bytes = str(raw_response).encode("utf-8") if raw_response else b""

            response_text = response_bytes.decode("utf-8")

            # Parse SSE data frames if present (data: "chunk" format)
            if response_text.strip().startswith("data:"):
                parts = []
                for line in response_text.split("\n"):
                    line = line.strip()
                    if line.startswith("data:"):
                        chunk = line[5:].strip()
                        # Remove surrounding quotes if present
                        if chunk.startswith('"') and chunk.endswith('"'):
                            chunk = json.loads(chunk)
                        parts.append(chunk)
                response_text = "".join(parts)
            else:
                # Try to parse as JSON and extract the text
                try:
                    parsed = json.loads(response_text)
                    if isinstance(parsed, dict):
                        response_text = parsed.get("response", parsed.get("output", response_text))
                except (json.JSONDecodeError, ValueError):
                    pass

            logger.info(f"Agent responded agent_id={agent_id} len={len(response_text)}")

            return {
                "agentId": agent_id,
                "response": response_text.strip(),
                "agentName": agent_name,
            }

        except client.exceptions.ResourceNotFoundException:
            raise AgentUnreachableError(
                f"Agent runtime not found: {agent_arn}",
                {"agent_id": agent_id, "agent_arn": agent_arn},
            )
        except client.exceptions.AccessDeniedException as e:
            raise AgentUnreachableError(
                f"Access denied invoking agent: {e}",
                {"agent_id": agent_id, "agent_arn": agent_arn},
            )
        except Exception as e:
            logger.error(f"Error invoking agent agent_id={agent_id}: {e}")
            raise AgentUnreachableError(
                f"Failed to invoke agent: {e}",
                {"agent_id": agent_id, "agent_url": agent_url},
            )

# Force CDK asset hash change - v4 SSE parsing fix 2026-03-07
