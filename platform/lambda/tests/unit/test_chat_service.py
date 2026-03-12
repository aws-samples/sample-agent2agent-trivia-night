"""Unit tests for the ChatService.

Mocks the MCP client (streamablehttp_client, ClientSession) and the
AgentService to test timeout handling, error responses, and successful
invocation without making real network calls.

Requirements: 4.3, 4.7, 4.8
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent_service import AgentNotFoundError
from services.chat_service import (
    AgentUnreachableError,
    ChatService,
    ChatServiceError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_service_mock(
    agent: Optional[Dict[str, Any]] = None,
    raise_not_found: bool = False,
    agent_id: str = "agent-123",
) -> MagicMock:
    """Build a mock AgentService that returns *agent* or raises NotFound."""
    mock_as = MagicMock()
    if raise_not_found:
        mock_as.get_agent.side_effect = AgentNotFoundError(agent_id)
    else:
        mock_as.get_agent.return_value = agent or {
            "agent_id": agent_id,
            "name": "TestAgent",
            "url": "https://agent.example.com/mcp",
            "description": "A test agent",
        }
    return mock_as


def _make_tool(name: str = "invoke") -> MagicMock:
    """Create a mock MCP tool descriptor."""
    tool = MagicMock()
    tool.name = name
    return tool


def _make_text_block(text: str) -> MagicMock:
    """Create a mock content block with a .text attribute."""
    block = MagicMock()
    block.text = text
    return block


def _make_call_tool_result(texts: list[str]) -> MagicMock:
    """Create a mock call_tool result with content blocks."""
    result = MagicMock()
    result.content = [_make_text_block(t) for t in texts]
    return result


# ---------------------------------------------------------------------------
# Successful invocation  (Requirement 4.3)
# ---------------------------------------------------------------------------

class TestSuccessfulInvocation:
    @patch("services.chat_service.streamablehttp_client")
    @patch("services.chat_service.ClientSession")
    def test_returns_response_with_required_fields(self, mock_session_cls, mock_http_client):
        """A successful MCP call returns agentId, response, and agentName."""
        # Set up the async context managers
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=MagicMock(tools=[_make_tool("invoke")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(["Hello from agent!"])
        )

        # ClientSession as async context manager
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        # streamablehttp_client as async context manager yielding (read, write, _)
        @asynccontextmanager
        async def fake_http_client(url):
            yield (AsyncMock(), AsyncMock(), None)

        mock_http_client.side_effect = fake_http_client

        agent_svc = _make_agent_service_mock()
        chat_svc = ChatService(agent_service=agent_svc)
        result = chat_svc.invoke_agent("agent-123", "Hello")

        assert result["agentId"] == "agent-123"
        assert result["response"] == "Hello from agent!"
        assert result["agentName"] == "TestAgent"

    @patch("services.chat_service.streamablehttp_client")
    @patch("services.chat_service.ClientSession")
    def test_concatenates_multiple_content_blocks(self, mock_session_cls, mock_http_client):
        """Multiple text blocks are joined with newlines."""
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=MagicMock(tools=[_make_tool("invoke")])
        )
        mock_session.call_tool = AsyncMock(
            return_value=_make_call_tool_result(["Part 1", "Part 2"])
        )

        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        @asynccontextmanager
        async def fake_http_client(url):
            yield (AsyncMock(), AsyncMock(), None)

        mock_http_client.side_effect = fake_http_client

        agent_svc = _make_agent_service_mock()
        chat_svc = ChatService(agent_service=agent_svc)
        result = chat_svc.invoke_agent("agent-123", "Hello")

        assert result["response"] == "Part 1\nPart 2"


# ---------------------------------------------------------------------------
# AgentNotFoundError  (Requirement 4.7 — agent doesn't exist)
# ---------------------------------------------------------------------------

class TestAgentNotFound:
    def test_raises_agent_not_found_error(self):
        """Chat with a non-existent agent raises AgentNotFoundError."""
        agent_svc = _make_agent_service_mock(raise_not_found=True)
        chat_svc = ChatService(agent_service=agent_svc)

        with pytest.raises(AgentNotFoundError):
            chat_svc.invoke_agent("agent-123", "Hello")


# ---------------------------------------------------------------------------
# AgentUnreachableError — MCP connection failure  (Requirement 4.7)
# ---------------------------------------------------------------------------

class TestAgentUnreachable:
    @patch("services.chat_service.streamablehttp_client")
    def test_connection_error_raises_unreachable(self, mock_http_client):
        """Network failure connecting to MCP endpoint raises AgentUnreachableError."""

        @asynccontextmanager
        async def failing_client(url):
            raise ConnectionError("Connection refused")
            yield  # noqa: unreachable — required for asynccontextmanager

        mock_http_client.side_effect = failing_client

        agent_svc = _make_agent_service_mock()
        chat_svc = ChatService(agent_service=agent_svc)

        with pytest.raises(AgentUnreachableError) as exc_info:
            chat_svc.invoke_agent("agent-123", "Hello")
        assert "Failed to communicate with agent" in exc_info.value.message

    def test_agent_with_no_url_raises_unreachable(self):
        """Agent record with no URL raises AgentUnreachableError."""
        agent_svc = _make_agent_service_mock(
            agent={"agent_id": "agent-123", "name": "NoUrl", "url": "", "description": "x"}
        )
        chat_svc = ChatService(agent_service=agent_svc)

        with pytest.raises(AgentUnreachableError) as exc_info:
            chat_svc.invoke_agent("agent-123", "Hello")
        assert "no registered URL" in exc_info.value.message

    @patch("services.chat_service.streamablehttp_client")
    @patch("services.chat_service.ClientSession")
    def test_no_tools_raises_error(self, mock_session_cls, mock_http_client):
        """Agent that exposes no tools raises ChatServiceError."""
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=MagicMock(tools=[])
        )

        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        @asynccontextmanager
        async def fake_http_client(url):
            yield (AsyncMock(), AsyncMock(), None)

        mock_http_client.side_effect = fake_http_client

        agent_svc = _make_agent_service_mock()
        chat_svc = ChatService(agent_service=agent_svc)

        with pytest.raises((ChatServiceError, AgentUnreachableError)):
            chat_svc.invoke_agent("agent-123", "Hello")


# ---------------------------------------------------------------------------
# Timeout enforcement — 25 seconds  (Requirement 4.8)
# ---------------------------------------------------------------------------

class TestTimeoutEnforcement:
    def test_timeout_constant_is_25(self):
        """ChatService.INVOCATION_TIMEOUT is 25 seconds."""
        assert ChatService.INVOCATION_TIMEOUT == 25

    @patch("services.chat_service.asyncio.run")
    def test_timeout_raises_unreachable(self, mock_run):
        """asyncio.TimeoutError during invocation raises AgentUnreachableError."""
        mock_run.side_effect = asyncio.TimeoutError()

        agent_svc = _make_agent_service_mock()
        chat_svc = ChatService(agent_service=agent_svc)

        with pytest.raises(AgentUnreachableError) as exc_info:
            chat_svc.invoke_agent("agent-123", "Hello")
        assert "timed out" in exc_info.value.message
        assert exc_info.value.details.get("timeout_seconds") == 25


# ---------------------------------------------------------------------------
# Error response structure
# ---------------------------------------------------------------------------

class TestErrorAttributes:
    def test_chat_service_error_has_error_code(self):
        err = ChatServiceError("test error")
        assert err.error_code == "AGENT_UNREACHABLE"
        assert err.message == "test error"
        assert err.details == {}

    def test_agent_unreachable_error_has_details(self):
        err = AgentUnreachableError("timeout", {"agent_url": "https://x.com"})
        assert err.error_code == "AGENT_UNREACHABLE"
        assert err.details["agent_url"] == "https://x.com"
