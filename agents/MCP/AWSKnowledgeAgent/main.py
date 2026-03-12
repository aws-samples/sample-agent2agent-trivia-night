from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

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