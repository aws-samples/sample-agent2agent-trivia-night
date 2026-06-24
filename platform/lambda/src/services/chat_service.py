"""
Chat service for invoking registered agents.

Uses HTTP requests with Cognito M2M bearer tokens to communicate
with agents deployed on AgentCore Runtime.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request
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
    """Invokes registered agents via HTTP with Cognito bearer token."""

    INVOCATION_TIMEOUT = 55

    def __init__(self, agent_service: Optional[AgentService] = None) -> None:
        self.agent_service = agent_service or AgentService()
        self._default_region = os.environ.get("AWS_REGION", "us-east-1")
        self._ssm_prefix = os.environ.get("SSM_PREFIX", "/Workshop/platform")

        # M2M token cache with TTL
        self._m2m_token: Optional[str] = None
        self._m2m_token_expiry: float = 0

        # SSM params cache (loaded once)
        self._m2m_config: Optional[Dict[str, str]] = None

        logger.info("Initialised ChatService")

    def _load_m2m_config(self) -> Dict[str, str]:
        """Load M2M client config from SSM Parameter Store (cached)."""
        if self._m2m_config is not None:
            return self._m2m_config

        ssm = boto3.client("ssm", region_name=self._default_region)
        prefix = self._ssm_prefix

        try:
            client_id = ssm.get_parameter(Name=f"{prefix}/m2m_client_id")["Parameter"]["Value"]
            client_secret = ssm.get_parameter(
                Name=f"{prefix}/m2m_client_secret", WithDecryption=True
            )["Parameter"]["Value"]
            user_pool_domain = ssm.get_parameter(
                Name=f"{prefix}/user_pool_domain"
            )["Parameter"]["Value"]
        except Exception as e:
            raise ChatServiceError(
                f"Failed to load M2M config from SSM: {e}",
                error_code="CONFIG_ERROR",
            )

        self._m2m_config = {
            "client_id": client_id,
            "client_secret": client_secret,
            "token_endpoint": (
                f"https://{user_pool_domain}.auth.{self._default_region}"
                f".amazoncognito.com/oauth2/token"
            ),
        }
        logger.info("Loaded M2M config from SSM")
        return self._m2m_config

    def _get_bearer_token(self) -> str:
        """Get a valid M2M bearer token, refreshing if expired (with 60s buffer)."""
        if self._m2m_token and time.time() < self._m2m_token_expiry - 60:
            return self._m2m_token

        config = self._load_m2m_config()
        credentials = base64.b64encode(
            f"{config['client_id']}:{config['client_secret']}".encode()
        ).decode()

        req = urllib.request.Request(
            config["token_endpoint"],
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                token_data = json.loads(resp.read().decode())
                self._m2m_token = token_data["access_token"]
                self._m2m_token_expiry = time.time() + token_data.get("expires_in", 3600)
                logger.info("Acquired M2M bearer token")
                return self._m2m_token
        except Exception as e:
            raise ChatServiceError(
                f"Failed to fetch M2M bearer token: {e}",
                error_code="AUTH_ERROR",
            )

    def _region_from_arn(self, arn: str) -> str:
        """Extract region from an ARN like arn:aws:bedrock-agentcore:us-east-1:..."""
        parts = arn.split(":")
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        return self._default_region

    def _extract_arn_from_url(self, url: str) -> Optional[str]:
        """Extract the AgentCore Runtime ARN from a registered URL.

        URLs registered by our scripts look like:
        https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A<account>%3Aruntime%2F<id>/invocations/

        The ARN is URL-encoded in the path between /runtimes/ and /invocations/.
        """
        if "bedrock-agentcore" not in url:
            return None

        from urllib.parse import unquote

        decoded_url = unquote(url)

        # Primary: find the ARN embedded in the decoded URL
        arn_prefix = "arn:aws:bedrock-agentcore:"
        arn_start = decoded_url.find(arn_prefix)
        if arn_start != -1:
            arn_rest = decoded_url[arn_start:]
            for terminator in ["/invocations", "/runtime-endpoint"]:
                if terminator in arn_rest:
                    arn_rest = arn_rest[:arn_rest.index(terminator)]
                    break
            return arn_rest.rstrip("/")

        # Fallback: reconstruct ARN from path segments (older URL format)
        parts = decoded_url.rstrip("/").split("/")
        try:
            runtime_idx = parts.index("runtimes")
            runtime_id = parts[runtime_idx + 1]
        except (ValueError, IndexError):
            try:
                runtime_idx = parts.index("runtime")
                runtime_id = parts[runtime_idx + 1]
            except (ValueError, IndexError):
                return None

        try:
            hostname = url.split("//")[1].split("/")[0]
            region = hostname.split(".")[1]
        except (IndexError, AttributeError):
            region = self._default_region

        try:
            sts = boto3.client("sts")
            account_id = sts.get_caller_identity()["Account"]
        except Exception:
            account_id = "unknown"

        return f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/{runtime_id}"

    def _build_invocation_url(self, agent_url: str, agent_arn: Optional[str]) -> str:
        """Build the direct HTTPS invocation URL for an AgentCore agent.

        If the registered URL already looks like an AgentCore invocations
        endpoint, return it directly. Otherwise, construct the URL from the ARN.
        """
        if "bedrock-agentcore" in agent_url and "/invocations" in agent_url:
            return agent_url.rstrip("/")

        if agent_arn:
            from urllib.parse import quote
            region = self._region_from_arn(agent_arn)
            encoded_arn = quote(agent_arn, safe="")
            return (
                f"https://bedrock-agentcore.{region}.amazonaws.com"
                f"/runtimes/{encoded_arn}/invocations"
            )

        return agent_url.rstrip("/")

    @staticmethod
    def _build_a2a_payload(message: str) -> bytes:
        """Build an A2A JSON-RPC 2.0 message/send payload."""
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": str(uuid.uuid4()),
                    "parts": [{"kind": "text", "text": message}],
                }
            },
        }
        return json.dumps(payload).encode()

    @staticmethod
    def _parse_a2a_response(response_text: str) -> str:
        """Extract text content from an A2A JSON-RPC response."""
        try:
            parsed = json.loads(response_text)

            # JSON-RPC error
            if "error" in parsed:
                error = parsed["error"]
                return f"Agent error: {error.get('message', str(error))}"

            result = parsed.get("result", parsed)

            # 1. Task with artifacts: {artifacts: [{parts: [...]}]}
            artifacts = result.get("artifacts", [])
            if artifacts:
                texts = []
                for artifact in artifacts:
                    for part in artifact.get("parts", []):
                        if part.get("kind") == "text" and part.get("text"):
                            texts.append(part["text"])
                if texts:
                    return "".join(texts)

            # 2. Task with status message: {status: {message: {parts: [...]}}}
            message = result.get("status", {}).get("message") or result.get("message")
            if message and "parts" in message:
                texts = []
                for part in message["parts"]:
                    if part.get("kind") == "text" and part.get("text"):
                        texts.append(part["text"])
                if texts:
                    return "".join(texts)

            # 3. Parts at top level
            if "parts" in result:
                texts = [p["text"] for p in result["parts"] if p.get("kind") == "text" and p.get("text")]
                if texts:
                    return "".join(texts)

            return response_text
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
                        try:
                            chunk = json.loads(chunk)
                        except json.JSONDecodeError:
                            pass
                    parts.append(chunk)
            return "".join(parts)

        return response_text

    def invoke_agent(self, agent_id: str, message: str) -> Dict[str, Any]:
        """Look up an agent and invoke it via AgentCore Runtime with A2A protocol."""
        logger.info(f"Invoking agent agent_id={agent_id}")

        agent = self.agent_service.get_agent(agent_id)
        agent_url = agent.get("url", "")
        agent_name = agent.get("name", "Unknown Agent")

        if not agent_url:
            raise AgentUnreachableError("Agent has no registered URL", {"agent_id": agent_id})

        logger.info(f"Agent URL/ARN: {agent_url}")

        if agent_url.startswith("arn:aws:bedrock-agentcore:"):
            agent_arn = agent_url
        else:
            agent_arn = self._extract_arn_from_url(agent_url)

        invocation_url = self._build_invocation_url(agent_url, agent_arn)
        logger.info(f"Invocation URL: {invocation_url}")

        try:
            payload = self._build_a2a_payload(message)
            session_id = str(uuid.uuid4())
            bearer_token = self._get_bearer_token()

            req = urllib.request.Request(
                invocation_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {bearer_token}",
                    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=55) as resp:  # nosec B310
                response_bytes = resp.read()

            response_text = response_bytes.decode("utf-8")
            response_text = self._parse_a2a_response(response_text)

            logger.info(f"Agent responded agent_id={agent_id} len={len(response_text)}")

            return {
                "agentId": agent_id,
                "response": response_text.strip(),
                "agentName": agent_name,
            }

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            logger.error(f"HTTP {e.code} invoking agent agent_id={agent_id}: {body}")
            raise AgentUnreachableError(
                f"Agent returned HTTP {e.code}: {body[:200]}",
                {"agent_id": agent_id, "http_status": e.code},
            )
        except urllib.error.URLError as e:
            raise AgentUnreachableError(
                f"Failed to reach agent: {e.reason}",
                {"agent_id": agent_id, "invocation_url": invocation_url},
            )
        except ChatServiceError:
            raise
        except Exception as e:
            logger.error(f"Error invoking agent agent_id={agent_id}: {e}")
            raise AgentUnreachableError(
                f"Failed to invoke agent: {e}",
                {"agent_id": agent_id, "agent_url": agent_url},
            )
