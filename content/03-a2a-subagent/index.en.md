---
title: "Connect to a subagent using A2A"
weight: 40
---

## 1. Find A2A-compatible agents in the registry

### 1.1 Find the following stack outputs for your Workshop Studio account:

- PlatformURL
- PlatformUsername
- PlatformPassword

![Platform Outputs Editor](/static/platform.png)

### 1.2. Navigate to the PlatformURL and login using the PlatformUsername and PlatformPassword values.

![Platform Login](/static/platform_login.png)

### 1.3. Select **Agent Registry > Agents** from the side bar.

![Platform Agents](/static/platform_agents.png)

### 1.4. Search for **Calculator**.

![Platform Search](/static/platform_search.png)

### 1.5. Select the **JSON** option on the Calculator Agent card.

![Platform Calculator Card](/static/platform_calculator_card.png)

### 1.6. Scroll to the bottom of the window and find the "url" value. You'll use this in the next section

![Platform Calculator URL](/static/platform_calculator_url.png)

## 2. Update the Orchestration agent code

Replace the Orchestrator agent code in `/workshop/OrchestratorAgent/src/main.py` with the following, adding the url for the Calculator agent in the `KNOWN_AGENT_URLS` list:

:::code{showCopyAction=true language=python}
import asyncio
import json
import os
import pprint

import jwt
from bedrock_agentcore.identity.auth import requires_access_token, requires_api_key
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
from model.load import load_model
from strands import Agent, tool
from strands.tools.mcp.mcp_client import MCPClient
from strands_tools.a2a_client import A2AClientToolProvider

KNOWN_AGENT_URLS = [""REPLACE_WITH_AN_AGENT_URL"]

encoded_arn = os.environ["AWS_KNOWLEDGE_AGENT_ARN"].replace(":", "%3A").replace("/", "%2F")
REGION = os.getenv("AWS_REGION")
MCP_ENDPOINT = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

@requires_access_token(
    provider_name="cognito-provider",
    scopes=[],  # MCP-specific scopes - adjust as needed
    auth_flow="M2M",  # M2M authentication flow
)
async def get_authenticated_mcp_client(*, access_token: str):
    headers = {"Authorization": f"Bearer {access_token}"}

    # Get timeout configuration from environment with reasonable defaults
    http_timeout = float(os.environ.get("HTTP_TIMEOUT", 30))
    sse_read_timeout = float(os.environ.get("SSE_READ_TIMEOUT", 300))

    return MCPClient(
        lambda: streamablehttp_client(
            url=MCP_ENDPOINT,
            headers=headers,
            timeout=http_timeout,  # HTTP operations timeout
            sse_read_timeout=sse_read_timeout,  # SSE read timeout
        )
    )

@requires_access_token(
    provider_name="cognito-provider",
    scopes=[],  # MCP-specific scopes - adjust as needed
    auth_flow="M2M",  # M2M authentication flow
)
async def get_authenticated_a2a_client(*, access_token: str):
    headers = {"Authorization": f"Bearer {access_token}"}

    # Get timeout configuration from environment with reasonable defaults
    http_timeout = float(os.environ.get("HTTP_TIMEOUT", 300))

    return A2AClientToolProvider(
        known_agent_urls=KNOWN_AGENT_URLS,
        httpx_client_args={
            "headers": headers,
            "timeout": http_timeout
        }
        )

app = BedrockAgentCoreApp()
log = app.logger

@app.entrypoint
async def invoke(payload, context):
    session_id = getattr(context, "session_id", "default")
    user_id = payload.get("user_id") or "default-user"

    auth_header = context.request_headers.get("Authorization")
    if auth_header:
        # Remove "Bearer " prefix if present
        token = (
            auth_header.replace("Bearer ", "")
            if auth_header.startswith("Bearer ")
            else auth_header
        )
        try:
            # Skip signature validation as agent runtime has validated the token already.
            claims = jwt.decode(token, options={"verify_signature": False})
            app.logger.info("Incoming Oauth claims (For user):")
            pprint.pprint(claims)
        except jwt.InvalidTokenError as e:
            app.logger.exception("Invalid JWT token: %s", e)

    mcp_client = await get_authenticated_mcp_client()
    a2a_client = await get_authenticated_a2a_client()

    with mcp_client as client:
        # Get MCP Tools
        tools = client.list_tools_sync() + a2a_client.tools

        # Create agent
        agent = Agent(
            model=load_model(),
            system_prompt="""
                You are a helpful assistant intended to help answer trivia questions about life science, AI, and cloud computing topics. Use tools when appropriate.
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
:::

## 3. Redeploy

Redeploy the Orchestration agent

:::code{showCopyAction=true language=bash}
cd /workshop/OrchestratorAgent
agentcore configure --non-interactive \
  --requirements-file requirements.txt \
  --authorizer-config "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$COGNITO_DISCOVERY_URL\",\"allowedClients\":[\"$COGNITO_CLIENT_ID\"]}}" \
  --request-header-allowlist "Authorization"

agentcore deploy --env AWS_KNOWLEDGE_AGENT_ARN=$AWS_KNOWLEDGE_AGENT_ARN
:::

## 4. Test the multi-agent communication over A2A

Run the following command to invoke the orchestrator agent, which in turn invokes the Calculator via A2A.

:::code{showCopyAction=true language=bash}
export USERNAME=$(aws ssm get-parameters \
  --names /Workshop/platform/username \
  --query "Parameters[*].Value" \
  --output text)

export PASSWORD=$(aws ssm get-parameters \
  --names /Workshop/platform/password \
  --with-decryption \
  --query "Parameters[*].Value" \
  --output text)

export BEARER_TOKEN=$(aws cognito-idp initiate-auth \
  --client-id $COGNITO_CLIENT_ID \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=$USERNAME,PASSWORD=$PASSWORD \
  --region "us-east-1" | jq -r '.AuthenticationResult.AccessToken')

agentcore invoke '{"prompt": "Ask the calculator agent to find the square root of 1764"}' --bearer-token $BEARER_TOKEN
:::

Congratulations! You have successfully deployed a team of agents communicating over A2A. In the next lab, you'll add additional A2A agents and use them to master the trivia challenge!
