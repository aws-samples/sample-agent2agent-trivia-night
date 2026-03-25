#!/bin/bash

STACK_OPERATION=$1

# Anchor to the repo root regardless of where this script is invoked from
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Install uv and add it to PATH for the rest of this script
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version

cd "$REPO_ROOT/agents/A2A/CalculatorAgent"

if [[ "$STACK_OPERATION" == "Create" || "$STACK_OPERATION" == "Update" ]]; then
    echo "Hello"
    uv run --with bedrock-agentcore-starter-toolkit agentcore configure \
      --non-interactive \
      -n CalculatorAgent \
      -rf requirements.txt \
      -dt "direct_code_deploy" \
      -rt "PYTHON_3_13" \
      -e main.py \
      -p A2A \
      -dm
    uv run agentcore deploy

elif [ "$STACK_OPERATION" == "Delete" ]; then
    echo "Goodbye"
    uv run --with bedrock-agentcore-starter-toolkit agentcore configure \
      --non-interactive \
      -n CalculatorAgent \
      -rf requirements.txt \
      -dt "direct_code_deploy" \
      -rt "PYTHON_3_13" \
      -e main.py \
      -p A2A \
      -dm
    uv run agentcore destroy --force

else
    echo "Invalid stack operation!"
    exit 1
fi
