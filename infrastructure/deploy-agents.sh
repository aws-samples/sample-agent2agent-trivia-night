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
    uv run --with bedrock-agentcore-starter-toolkit agentcore configure \
      --non-interactive \
      -n CalculatorAgent \
      -rf requirements.txt \
      -dt "direct_code_deploy" \
      -rt "PYTHON_3_13" \
      -e main.py \
      -p A2A \
      -dm
    uv run "$REPO_ROOT/scripts/deploy_and_register.py" \
      --name "CalculatorAgent" \
      --description "A simple A2A example with access to a calculator tool." \
      --api-url "$REGISTRY_API_URL"

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
