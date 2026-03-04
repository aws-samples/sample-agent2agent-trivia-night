"""
AWS Knowledge Agent using Strands + AgentCore Runtime
Connects to the AWS Knowledge MCP Server via Streamable HTTP transport.
Wrapped with mcp.tool() to provide an MCP server for Agent-as-tool orchestration pattern
"""

from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

# AWS Knowledge MCP Server via Streamable HTTP
aws_knowledge_client = MCPClient(
    lambda: streamablehttp_client("https://knowledge-mcp.global.api.aws"),
    tool_filters={
        "allowed": ["aws___search_documentation", "aws___read_documentation"]
    },
)

model = BedrockModel(
    model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name="us-east-1",
    temperature=0.5,
    max_tokens=4096,
)

SYSTEM_PROMPT = """You are an AWS expert assistant with access to the official AWS Knowledge base.
Use the available tools to search and read AWS documentation to provide accurate, up-to-date answers.
Always cite the documentation source when answering questions."""

mcp = FastMCP(
    "aws-knowledge-agent",
    stateless_http=True,
    host="0.0.0.0",
    port=8000,
)


@mcp.tool()
def invoke(request: str = "Hello"):
    """
    Respond to use requests using the AWS Knowledge MCP Server, a fully managed remote MCP server that provides
    up-to-date documentation, code samples, knowledge about the regional availability of AWS APIs and
    CloudFormation resources, and other official AWS content.
    """

    agent = Agent(
        model=model,
        tools=[aws_knowledge_client],
        system_prompt=SYSTEM_PROMPT,
    )
    return [
        content["text"]
        for content in agent(request).message["content"]
        if "text" in content
    ]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

# Uncomment to test locally using MCP inspector
# npx @modelcontextprotocol/inspector 
# if __name__ == "__main__":
#     import uvicorn
#     from starlette.middleware.cors import CORSMiddleware
#     app = mcp.streamable_http_app()
#     app.add_middleware(
#         CORSMiddleware,
#         allow_origins=["*"],
#         allow_methods=["*"],
#         allow_headers=["*"],
#     )
#     uvicorn.run(app, host="0.0.0.0", port=8000)
