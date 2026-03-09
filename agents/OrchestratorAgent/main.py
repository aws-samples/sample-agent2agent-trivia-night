from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
import os
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands.tools.mcp import MCPClient
import jwt
import json
import boto3
import base64
import urllib

app = BedrockAgentCoreApp()
log = app.logger
_agent = None


REGION = os.getenv("AWS_REGION")
POOL_NAME = "CognitoUserPool"
MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
AWS_KNOWLEDGE_AGENT_ARN = "arn:aws:bedrock-agentcore:XXX:YYY:runtime/ZZZ"


def get_ssm_param(ssm, path: str) -> str:
    return ssm.get_parameter(Name=path)["Parameter"]["Value"]


def get_m2m_client_secret(user_pool_id: str, client_id: str, region: str) -> str:
    cognito = boto3.client("cognito-idp", region_name=region)
    response = cognito.describe_user_pool_client(
        UserPoolId=user_pool_id, ClientId=client_id
    )
    return response["UserPoolClient"]["ClientSecret"]


def fetch_token(token_endpoint: str, client_id: str, client_secret: str) -> str:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        token_endpoint,
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]


def get_bearer_token(pool_name: str, region: str) -> str:
    ssm = boto3.client("ssm", region_name=region)
    prefix = f"/{pool_name}/m2m"
    user_pool_id = get_ssm_param(ssm, f"{prefix}/user-pool-id")
    client_id = get_ssm_param(ssm, f"{prefix}/client-id")
    token_endpoint = get_ssm_param(ssm, f"{prefix}/token-endpoint")
    client_secret = get_m2m_client_secret(user_pool_id, client_id, region)
    return fetch_token(token_endpoint, client_id, client_secret)


token = get_bearer_token(POOL_NAME, REGION)
print(token)
# Define a collection of tools used by the model
tools = []

# Add example remote MCP Server
# MCP_ENDPOINT = "https://mcp.exa.ai/mcp"
encoded_arn = AWS_KNOWLEDGE_AGENT_ARN.replace(":", "%3A").replace("/", "%2F")
MCP_ENDPOINT = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

mcp_client = MCPClient(
    lambda: streamablehttp_client(
        url=MCP_ENDPOINT, headers={"Authorization": f"Bearer {token}"}
    )
)
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
