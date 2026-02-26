"""
AWS Knowledge Agent using Strands + AgentCore Runtime
Connects to the AWS Knowledge MCP Server via mcp-remote.
Wrapped with BedrockAgentCoreApp for deployment to AgentCore Runtime.
"""

from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

# AWS Knowledge MCP Server via mcp-remote
aws_knowledge_client = MCPClient(
    lambda: stdio_client(
        StdioServerParameters(
            command="npx",
            args=["mcp-remote", "https://knowledge-mcp.global.api.aws"],
        )
    ),
    tool_filters={"allowed": ["aws___search_documentation", "aws___read_documentation"]},
)

# Bedrock model (Claude Sonnet 4 by default)
model = BedrockModel(
    model_id="anthropic.claude-sonnet-4-20250514-v1:0",
    region_name="us-east-1",
    temperature=0.2,
    max_tokens=4096,
)

SYSTEM_PROMPT = """You are an AWS expert assistant with access to the official AWS Knowledge base.
Use the available tools to search and read AWS documentation to provide accurate, up-to-date answers.
Always cite the documentation source when answering questions."""


@app.entrypoint
def invoke(payload, context):
    user_message = payload.get("prompt", "Hello!")
    agent = Agent(
        model=model,
        tools=[aws_knowledge_client],
        system_prompt=SYSTEM_PROMPT,
    )
    response = agent(user_message)
    return {"response": str(response)}


if __name__ == "__main__":
    app.run()
