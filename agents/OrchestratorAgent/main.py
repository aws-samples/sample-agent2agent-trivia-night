from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
import os
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient
import jwt
import json


app = BedrockAgentCoreApp()
log = app.logger
_agent = None


REGION = os.getenv("AWS_REGION")
MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"

# Define a collection of tools used by the model
tools = []


# Define a simple function tool
@tool
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers"""
    return a + b


tools.append(add_numbers)

# Add example remote MCP Server
EXAMPLE_MCP_ENDPOINT = "https://mcp.exa.ai/mcp"
mcp_client = MCPClient(lambda: streamablehttp_client(EXAMPLE_MCP_ENDPOINT))
tools.append(mcp_client)


def get_or_create_agent():
    global _agent
    if _agent is None:
        _agent = Agent(
            model=BedrockModel(model_id=MODEL_ID),
            system_prompt="""
                You are a helpful assistant intended to help answer trivia questions about life science, AI, and cloud computing topics. Use tools when appropriate.
            """,
            tools=tools,
        )
    return _agent


@app.entrypoint
async def invoke(payload, context):

    if context.request_headers:
        auth_header = context.request_headers.get("Authorization")

        # Remove "Bearer " prefix if present
        token = (
            auth_header.replace("Bearer ", "")
            if auth_header.startswith("Bearer ")
            else auth_header
        )
        try:
            # Skip signature validation as agent runtime has validated the token already.
            claims = jwt.decode(token, options={"verify_signature": False})
            app.logger.info("Claims: %s", json.dumps(claims))
        except jwt.InvalidTokenError as e:
            app.logger.exception("Invalid JWT token: %s", e)

    log.info("Invoking Agent.....")

    agent = get_or_create_agent()

    # Execute and format response
    stream = agent.stream_async(payload.get("prompt"))

    async for event in stream:
        # Handle Text parts of the response
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
