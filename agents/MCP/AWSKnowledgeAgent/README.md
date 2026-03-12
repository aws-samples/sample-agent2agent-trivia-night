# AWS Knowledge Agent

## Summary

AWS Knowledge Agent using Strands + AgentCore Runtime
Connects to the AWS Knowledge MCP Server via mcp-remote.
Wrapped with BedrockAgentCoreApp for deployment to AgentCore Runtime.

## Deployment

1. (If needed) Install uv with `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. `uv add bedrock-agentcore-starter-toolkit`
3. Get Cognito configuration information by running

```bash
echo
export COGNITO_DISCOVERY_URL=$(aws ssm get-parameters \
  --names /Workshop/platform/cognito_discovery_url \
  --query "Parameters[*].Value" \
  --output text)
echo -e "Discovery URL:\n$COGNITO_DISCOVERY_URL"
echo
export COGNITO_M2M_CLIENT_ID=$(aws ssm get-parameters \
  --names /Workshop/platform/m2m_client_id \
  --query "Parameters[*].Value" \
  --output text)
echo -e "Client ID:\n$COGNITO_M2M_CLIENT_ID"
echo
```

1. Configure agent by running

```bash
uv run agentcore configure \
--non-interactive \
-e main.py \
-n AWSKnowledgeAgent2 \
-rt PYTHON_3_13 \
-rf requirements.txt \
-do -dm -p MCP -r $AWS_REGION \
--authorizer-config "{\"customJWTAuthorizer\": {\"discoveryUrl\": \"$COGNITO_DISCOVERY_URL\", \"allowedClients\": [\"$COGNITO_M2M_CLIENT_ID\"]}}"
```

1. Deploy agent by running `uv run agentcore deploy`.
