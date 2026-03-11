import os
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient

MCP_ENDPOINT = "https://subwayinfo.nyc/mcp"
MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = os.getenv("AWS_REGION")

app = BedrockAgentCoreApp()
log = app.logger

def get_streamable_http_mcp_client() -> MCPClient:
    """
    Returns an MCP Client compatible with Strands
    """
    # to use an MCP server that supports bearer authentication, add headers={"Authorization": f"Bearer {access_token}"}
    return MCPClient(lambda: streamablehttp_client(MCP_ENDPOINT))

# Import AgentCore Gateway as Streamable HTTP MCP Client
mcp_client = get_streamable_http_mcp_client()

@app.entrypoint
async def invoke(payload, context):

    with mcp_client as client:
        # Get MCP Tools
        tools = client.list_tools_sync()

        # Create agent
        agent = Agent(
            model=BedrockModel(model_id=MODEL_ID),
            system_prompt="""
                You are a helpful AI assist with knowledge of New York City transit data.
                You can help answer questions such as:

                - Should I leave now or wait 10 minutes?
                - What's actually running right now?
                - Plan my route avoiding delays
                - Track a specific train
                - What's the situation with my line?
                """,
            tools=tools,
        )

        # Execute and format response
        stream = agent.stream_async(payload.get("prompt"))

        async for event in stream:
            # Handle Text parts of the response
            if "data" in event and isinstance(event["data"], str):
                yield event["data"]


if __name__ == "__main__":
    app.run()
