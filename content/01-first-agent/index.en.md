---
title: "Building your first agent"
weight: 20
---

## 1. Create basic agent

### 1.1. Generate agent scaffold using the AgentCore CLI

:::code{showCopyAction=true language=bash}
agentcore create -p OrchestratorAgent --non-interactive
cd OrchestratorAgent
:::

### 1.2. Deploy the agent to Amazon Bedrock AgentCore Runtime

:::code{showCopyAction=true language=bash}
agentcore deploy
:::

### 1.3. Invoke agent

:::code{showCopyAction=true language=bash}
agentcore invoke '{"prompt": "Hello"}'
:::

## 2. Update agent with Kiro

### 2.1 Start Kiro CLI

:::code{showCopyAction=true language=bash}
kiro-cli
:::

### 2.2. Use Kiro to understand the default agent code

:::code{showCopyAction=true language=bash}
Explain the agent code in /workshop/OrchestratorAgent/src/main.py
:::

:::code
I'll read the main.py file to explain the agent code...
:::

### 2.3. Update the system prompt for your trivia use case

:::code{showCopyAction=true language=bash}
Update the system prompt for the agent to say it is intended to help answer trivia questions about life science, AI, and cloud computing topics.
:::

Review and approve the suggested changes. When the updates are complete, exit Kiro CLI by pressing **Ctrl/Cmd + C** or by typing `/quit`

### 2.4. Deploy updated agent code to AgentCore Runtime

:::code{showCopyAction=true language=bash}
agentcore deploy
:::

### 2.5. Test updated agent

:::code{showCopyAction=true language=bash}
agentcore invoke '{"prompt": "Hello"}'
:::

:::code
Hello! I'm here to help you answer trivia questions about life science, AI, and cloud computing topics...
:::

## 3. Update inbound authentication

By default, agents deployed to AgentCore Runtime use SigV4/IAM inbound authentication. Let's switch that to OAuth2, using a predeployed Amazon Cognito UserPool as the identity provider.

### 3.1. Get Cognito configuration

Run the following to retrieve the application client ID and discovery URL from Amazon Cognito.

:::code{showCopyAction=true language=bash}
export COGNITO_CLIENT_ID=$(aws ssm get-parameters \
  --names /Workshop/platform/cognito_client_id \
  --query "Parameters[*].Value" \
  --output text)
:::

:::code{showCopyAction=true language=bash}
export COGNITO_DISCOVERY_URL=$(aws ssm get-parameters \
  --names /Workshop/platform/cognito_discovery_url \
  --query "Parameters[*].Value" \
  --output text)
:::

### 3.2. Update agent auth configuration and redeploy

:::code{showCopyAction=true language=bash}
printf '%s\n%s\n%s\n%s\n%s\n' "PyJWT" "strands-agents" "strands-agents-tools[a2a_client]" "bedrock-agentcore" "mcp>=1.0.0" > /workshop/OrchestratorAgent/src/requirements.txt
agentcore configure --non-interactive \
  --requirements-file requirements.txt \
  --authorizer-config "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$COGNITO_DISCOVERY_URL\",\"allowedClients\":[\"$COGNITO_CLIENT_ID\"]}}" \
  --request-header-allowlist "Authorization"
agentcore deploy
:::

### 3.3. Try to invoke the agent without a bearer token

This command will now return an AccessDeniedException since it's missing the required OAuth token.

:::code{showCopyAction=true language=bash}
agentcore invoke '{"prompt": "Hello"}'
:::

## 4. Log in to Cognito using app username and password

Run the following to log into Cognito and generate a auth token:

:::code{showCopyAction=true language=bash}
export USERNAME=$(aws ssm get-parameters \
  --names /Workshop/platform/username \
  --query "Parameters[*].Value" \
  --output text)
:::

:::code{showCopyAction=true language=bash}
export PASSWORD=$(aws ssm get-parameters \
  --names /Workshop/platform/password \
  --with-decryption \
  --query "Parameters[*].Value" \
  --output text)
:::

:::code{showCopyAction=true language=bash}
export BEARER_TOKEN=$(aws cognito-idp initiate-auth \
  --client-id $COGNITO_CLIENT_ID \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=$USERNAME,PASSWORD=$PASSWORD \
  --region "us-east-1" | jq -r '.AuthenticationResult.AccessToken')
echo "Bearer token is $BEARER_TOKEN"
:::

Decode the token and inspect the contents by running the following command.

:::code{showCopyAction=true language=bash}
jq -R 'split(".") | .[1] | @base64d | fromjson' <<< $BEARER_TOKEN
:::

This is the information that AgentCore Identity will use to authenticate the incoming request.

## 5. Invoke agent using Cognito auth token

:::code{showCopyAction=true language=bash}
agentcore invoke '{"prompt": "Hello"}' --bearer-token $BEARER_TOKEN
:::

Congratulations! You have successfully deployed a scalable AI agent secured with OAuth2. In the next lab, we'll connect to a subagent using the Model Context Protocol (MCP).
