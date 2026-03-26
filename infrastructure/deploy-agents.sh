#!/bin/bash

STACK_OPERATION=$1
AGENT_ASSET_BUCKET=$2
REGISTRY_API_URL=$3

# Anchor to the repo root regardless of where this script is invoked from
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT/agents/A2A/CalculatorAgent"

if [[ "$STACK_OPERATION" == "Create" || "$STACK_OPERATION" == "Update" ]]; then
    echo $STACK_OPERATION
    echo $AGENT_ASSET_BUCKET
    echo $REGISTRY_API_URL

    # Install uv and add it to PATH for the rest of this script
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    uv --version

    # Get Cognito information
    M2M_TOKEN=$(uv run "$REPO_ROOT/scripts/get_m2m_token.py")
    export DISCOVERY_URL=$(echo "$M2M_TOKEN" | jq -r '.discovery_url')
    export CLIENT_ID=$(echo "$M2M_TOKEN" | jq -r '.client_id')
    export CLIENT_SECRET=$(echo "$M2M_TOKEN" | jq -r '.client_secret')
    export BEARER_TOKEN=$(echo "$M2M_TOKEN" | jq -r '.access_token')

    # Configure agent for A2A protocol
    uv run --with bedrock-agentcore-starter-toolkit agentcore configure \
      --non-interactive \
      -n CalculatorAgent \
      -rf requirements.txt \
      -dt "direct_code_deploy" \
      -rt "PYTHON_3_13" \
      -e main.py \
      -p A2A \
      -dm \
      --authorizer-config "{
        \"customJWTAuthorizer\": {
          \"discoveryUrl\": \"$DISCOVERY_URL\",
          \"allowedClients\": [\"$CLIENT_ID\"]
        }
      }"
    
    # Deploy to AgentCore Runtime
    uv run agentcore deploy --auto-update-on-conflict --env AGENT_ASSET_BUCKET=$AGENT_ASSET_BUCKET

    # Get the AgentCore Runtime ARN 
    export AGENT_ARN=$(grep 'agent_arn:' .bedrock_agentcore.yaml | awk '{print $2}')

    # Get the Agent Card and register it
    AGENT_CARD=$(uv run "$REPO_ROOT/scripts/get_agent_card.py")
    echo "$AGENT_CARD" | uv run "$REPO_ROOT/scripts/register_a2a.py" --api-url "$REGISTRY_API_URL"

    # uv run "$REPO_ROOT/scripts/deploy_and_register.py" \
    #   --name "CalculatorAgent" \
    #   --description "A simple A2A example with access to a calculator tool." \
    #   --skills "calculator" \
    #   --api-url "$REGISTRY_API_URL"

elif [ "$STACK_OPERATION" == "Delete" ]; then
    echo $STACK_OPERATION
    AGENT_NAME="CalculatorAgent"
    AGENT_RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
      --query "agentRuntimes[?agentRuntimeName=='$AGENT_NAME'].agentRuntimeId" \
      --output text)
    if [ -n "$AGENT_RUNTIME_ID" ] && [ "$AGENT_RUNTIME_ID" != "None" ]; then
        echo "Deleting agent runtime: $AGENT_RUNTIME_ID"
        aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id "$AGENT_RUNTIME_ID"
        echo "Deleted $AGENT_NAME ($AGENT_RUNTIME_ID)"
    else
        echo "No agent runtime found with name '$AGENT_NAME', skipping delete."
    fi

else
    echo "Invalid stack operation!"
    exit 1
fi
