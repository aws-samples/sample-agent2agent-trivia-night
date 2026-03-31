---
title: "Connect to a subagent using MCP"
weight: 30
---

## 1. Install example code from GitHub

Run the following command from the terminal to download the example code for this workshop.

Make sure you are in the parent folder:
```bash
cd /workshop/
```


```bash
git clone https://github.com/aws-samples/sample-agent2agent-trivia-night.git /workshop/sample-agent2agent-trivia-night
```

## 2. Explore the agent code

### 2.1. Navigate to the AWS Knowledge Agent

:::code{showCopyAction=true language=bash}
cd /workshop/sample-agent2agent-trivia-night/agents/MCP/AWSKnowledgeAgent
:::

### 2.1. Start Kiro CLI

:::code{showCopyAction=true language=bash}
kiro-cli
:::

### 2.2. Use Kiro to understand the default agent code

:::code{showCopyAction=true language=bash}
Explain the agent code in main.py
:::

:::code
I'll read and explain the AI agent code from that file...

This code implements an AWS Knowledge Agent that wraps an AI agent as an MCP (Model Context Protocol) tool. Here's what it does...
:::

When you're finished reviewing the AWS Knowledge Agent code, exit Kiro CLI by pressing **Ctrl/Cmd + C** or by typing `/quit`

## 3. Deploy the AWS Knowledge MCP Server

Get M2M credentials

:::code{showCopyAction=true language=bash}
export COGNITO_M2M_CLIENT_ID=$(aws ssm get-parameters \
  --names /Workshop/platform/m2m_client_id \
  --query "Parameters[*].Value" \
  --output text)

export COGNITO_DISCOVERY_URL=$(aws ssm get-parameters \
  --names /Workshop/platform/cognito_discovery_url \
  --query "Parameters[*].Value" \
  --output text)
:::

Deploy Server with MCP protocol

:::code{showCopyAction=true language=bash}
agentcore configure --non-interactive \
  --name AWSKnowledgeAgent \
  --requirements-file requirements.txt \
  --authorizer-config "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$COGNITO_DISCOVERY_URL\",\"allowedClients\":[\"$COGNITO_M2M_CLIENT_ID\"]}}" \
  --disable-memory \
  --protocol MCP
  
agentcore deploy
:::

## 4. Test AWS Knowledge Agent

### 4.1. Verify AWS Knowledge Agent deployment

Run the following command to export the AWS Knowledge Agent ARN as an environment variable named `AWS_KNOWLEDGE_AGENT_ARN`:

:::code{showCopyAction=true language=bash}
export AWS_KNOWLEDGE_AGENT_ARN=$(aws bedrock-agentcore-control list-agent-runtimes --query "agentRuntimes[?agentRuntimeName=='AWSKnowledgeAgent'].agentRuntimeArn" --output text)
echo $AWS_KNOWLEDGE_AGENT_ARN
:::

### 4.2. Run test script

:::code{showCopyAction=true language=bash}
uv run --python 3.13 --with boto3 --with mcp /workshop/sample-agent2agent-trivia-night/scripts/test_mcp.py
:::

:::code
=== Fetching Bearer Token ===
Token acquired...

=== Available Tools ===
  invoke:
Respond to use requests using the AWS Knowledge MCP Server, a fully managed remote MCP server that provides
up-to-date documentation, code samples, knowledge about the regional availability of AWS APIs and
CloudFormation resources, and other official AWS content...
:::

## 5. Update Orchestrator agent to call AWS Knowledge Agent using MCP

### 5.1. Update orchestrator code

Replace the Orchestrator agent code in `/workshop/OrchestratorAgent/src/main.py` with the following:

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

    with mcp_client as client:
        # Get MCP Tools
        tools = client.list_tools_sync()

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

### 5.2. Redeploy

:::alert{header="Warning" type="warning"}
Make sure to add the `a2a-sdk` module to the list of dependencies in `pyproject.toml`
:::

Navigate back to the Orchestrator agent folder and redeploy the agent with the subagent ARN as an environment variable.

:::code{showCopyAction=true language=bash}
cd /workshop/OrchestratorAgent
agentcore configure --non-interactive \
  --requirements-file requirements.txt \
  --authorizer-config "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$COGNITO_DISCOVERY_URL\",\"allowedClients\":[\"$COGNITO_CLIENT_ID\"]}}" \
  --request-header-allowlist "Authorization"

agentcore deploy --env AWS_KNOWLEDGE_AGENT_ARN=$AWS_KNOWLEDGE_AGENT_ARN
:::

## 6. Test the multi-agent communication over MCP

Run the following command to invoke the orchestrator agent, which in turn uses the AWS Knowledge MCP Server.

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

agentcore invoke '{"prompt": "Tell me about AgentCore Runtime"}' --bearer-token $BEARER_TOKEN
:::

Congratulations! You have successfully deployed a team of agents communicating over MCP. In the next lab, we'll expand our team using the A2A protocol.
