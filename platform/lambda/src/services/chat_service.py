"""
Chat service for invoking registered agents.

Uses HTTP requests with Cognito M2M bearer tokens to communicate
with agents deployed on AgentCore Runtime.
"""
import base64
import json
import os
import uuid
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.parse import urlencode

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
    """Invokes registered agents via HTTP with Cognito bearer token."""

    INVOCATION_TIMEOUT = 55

    def __init__(self, agent_service: Optional[AgentService] = None) -> None:
        self.agent_service = agent_service or AgentService()
        self._default_region = os.environ.get("AWS_REGION", "us-east-1")
        self._ssm_prefix = os.environ.get("SSM_PREFIX", "/Workshop/platform")
        self._m2m_token = None
        self._user_token = None
        self._ssm = boto3.client("ssm", region_name=self._default_region)
        self._cognito = boto3.client("cognito-idp", region_name=self._default_region)
        logger.info("Initialised ChatService")

    def _get_m2m_token(self) -> str:
        """Get a Cognito M2M bearer token using client_credentials flow (for A2A agents)."""
        if self._m2m_token:
            return self._m2m_token

        client_id = self._ssm.get_parameter(Name=f"{self._ssm_prefix}/m2m_client_id")["Parameter"]["Value"]
        client_secret = self._ssm.get_parameter(Name=f"{self._ssm_prefix}/m2m_client_secret", WithDecryption=True)["Parameter"]["Value"]
        domain = self._ssm.get_parameter(Name=f"{self._ssm_prefix}/user_pool_domain")["Parameter"]["Value"]

        token_url = f"https://{domain}.auth.{self._default_region}.amazoncognito.com/oauth2/token"
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        req = Request(
            token_url,
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:  # nosec B310
            self._m2m_token = json.loads(resp.read().decode())["access_token"]

        return self._m2m_token

    def _get_user_token(self) -> str:
        """Get a Cognito user access token using USER_PASSWORD_AUTH (for HTTP agents)."""
        if self._user_token:
            return self._user_token

        client_id = self._ssm.get_parameter(Name=f"{self._ssm_prefix}/cognito_client_id")["Parameter"]["Value"]
        username = self._ssm.get_parameter(Name=f"{self._ssm_prefix}/username")["Parameter"]["Value"]
        password = self._ssm.get_parameter(Name=f"{self._ssm_prefix}/password", WithDecryption=True)["Parameter"]["Value"]

        resp = self._cognito.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )
        self._user_token = resp["AuthenticationResult"]["AccessToken"]

        return self._user_token

    def _extract_arn_from_url(self, url: str) -> Optional[str]:
        """Extract the AgentCore Runtime ARN from a registered URL.

        URLs look like:
        https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3A.../invocations/
        """
        if "bedrock-agentcore" not in url:
            return None

        from urllib.parse import unquote

        # The URL contains a URL-encoded ARN between /runtimes/ and /invocations/
        decoded = unquote(url)
        # Look for ARN pattern in the decoded URL
        import re
        match = re.search(r'(arn:aws:bedrock-agentcore:[^:]+:[^:]+:runtime/[^/]+)', decoded)
        if match:
            return match.group(1)

        return None

    def invoke_agent(self, agent_id: str, message: str) -> Dict[str, Any]:
        """Look up an agent and invoke it via HTTP with bearer token."""
        logger.info(f"Invoking agent agent_id={agent_id}")

        agent = self.agent_service.get_agent(agent_id)
        agent_url = agent.get("url", "")
        agent_name = agent.get("name", "Unknown Agent")

        if not agent_url:
            raise AgentUnreachableError("Agent has no registered URL", {"agent_id": agent_id})

        # Convert ARN to invocation URL if needed
        if agent_url.startswith("arn:"):
            from urllib.parse import quote
            # Extract region from ARN: arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/ID
            arn_parts = agent_url.split(":")
            region = arn_parts[3] if len(arn_parts) > 3 else self._default_region
            encoded_arn = quote(agent_url, safe="")
            agent_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations/"

        logger.info(f"Agent URL: {agent_url}")

        # Determine protocol: A2A agents use 'text', HTTP agents use 'text/plain'
        input_modes = agent.get("defaultInputModes", [])
        is_a2a = "text" in input_modes and "text/plain" not in input_modes

        try:
            bearer_token = self._get_m2m_token() if is_a2a else self._get_user_token()
            session_id = str(uuid.uuid4())

            if is_a2a:
                payload = json.dumps({
                    "jsonrpc": "2.0",
                    "method": "message/send",
                    "id": session_id,
                    "params": {
                        "message": {
                            "role": "user",
                            "parts": [{"kind": "text", "text": message}],
                            "messageId": str(uuid.uuid4()),
                        },
                        "configuration": {"acceptedOutputModes": ["text"]},
                    },
                })
            else:
                payload = json.dumps({"prompt": message})

            req = Request(
                agent_url,
                data=payload.encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {bearer_token}",
                    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
                },
                method="POST",
            )

            with urlopen(req, timeout=self.INVOCATION_TIMEOUT) as resp:  # nosec B310
                response_text = resp.read().decode("utf-8")

            if is_a2a:
                # Parse JSONRPC response
                try:
                    parsed = json.loads(response_text)
                    if "result" in parsed:
                        result = parsed["result"]
                        # Extract text from A2A message parts
                        parts = []
                        for artifact in result.get("artifacts", []):
                            for part in artifact.get("parts", []):
                                if part.get("kind") == "text":
                                    parts.append(part["text"])
                        if parts:
                            response_text = "\n".join(parts)
                        elif isinstance(result, str):
                            response_text = result
                except (json.JSONDecodeError, ValueError):
                    pass
            else:
                # Parse HTTP agent response — may be plain text, JSON, or SSE
                try:
                    parsed = json.loads(response_text)
                    # Handle {"response": "..."} or {"output": "..."} or {"result": "..."}
                    for key in ("response", "output", "result", "text"):
                        if key in parsed and isinstance(parsed[key], str):
                            response_text = parsed[key]
                            break
                except (json.JSONDecodeError, ValueError):
                    pass

            # Parse SSE data frames if present
            if response_text.strip().startswith("data:"):
                parts = []
                for line in response_text.split("\n"):
                    line = line.strip()
                    if line.startswith("data:"):
                        chunk = line[5:].strip()
                        if chunk.startswith('"') and chunk.endswith('"'):
                            chunk = json.loads(chunk)
                        parts.append(chunk)
                response_text = "".join(parts)

            logger.info(f"Agent responded agent_id={agent_id} len={len(response_text)}")

            return {
                "agentId": agent_id,
                "response": response_text.strip(),
                "agentName": agent_name,
            }

        except Exception as e:
            logger.error(f"Error invoking agent agent_id={agent_id}: {e}")
            # Clear cached tokens in case they expired
            self._m2m_token = None
            self._user_token = None
            raise AgentUnreachableError(
                f"Failed to invoke agent: {e}",
                {"agent_id": agent_id, "agent_url": agent_url},
            )
