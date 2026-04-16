#!/bin/bash
#
# destroy.sh — Tear down the Agent-to-Agent Trivia Night workshop stacks.
#
# Deletes stacks in reverse deployment order to respect cross-stack dependencies.
#
# Usage:
#   ./scripts/destroy.sh                          # destroy in us-east-1 with defaults
#   ./scripts/destroy.sh us-west-2                # destroy in a specific region
#   ./scripts/destroy.sh us-east-1 MyPrefix       # destroy with a custom stack prefix
#
set -euo pipefail

REGION="${1:-us-east-1}"
STACK_PREFIX="${2:-Workshop}"

# Stack names (must match deploy.sh)
STACK_CODE_EDITOR="${STACK_PREFIX}-CodeEditor"
STACK_AGENTCORE="${STACK_PREFIX}-AgentCorePolicies"
STACK_PLATFORM="${STACK_PREFIX}-Platform"
STACK_AGENTS="${STACK_PREFIX}-Agents"

echo "============================================"
echo "  Agent-to-Agent Trivia Night — Destroyer"
echo "============================================"
echo "Region:       $REGION"
echo "Stack prefix: $STACK_PREFIX"
echo ""

delete_stack() {
  local stack_name="$1"

  # Check if the stack exists
  local status
  status=$(aws cloudformation describe-stacks \
    --region "$REGION" \
    --stack-name "$stack_name" \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null) || true

  if [ -z "$status" ] || [ "$status" = "None" ]; then
    echo "⏭️  $stack_name does not exist, skipping."
    echo ""
    return
  fi

  echo "--------------------------------------------"
  echo "Deleting: $stack_name  (status: $status)"
  echo "--------------------------------------------"

  aws cloudformation delete-stack \
    --region "$REGION" \
    --stack-name "$stack_name"

  echo "Waiting for $stack_name to be deleted..."
  aws cloudformation wait stack-delete-complete \
    --region "$REGION" \
    --stack-name "$stack_name"

  echo "✅ $stack_name deleted."
  echo ""
}

# Delete in reverse order of deployment
# 4. Agents (depends on Platform SSM parameter)
delete_stack "$STACK_AGENTS"

# 3. Platform (depends on nothing from other stacks, but must go before AgentCore/CodeEditor)
delete_stack "$STACK_PLATFORM"

# 2. AgentCore Policies (depends on CodeEditor export)
delete_stack "$STACK_AGENTCORE"

# 1. Code Editor (base stack)
delete_stack "$STACK_CODE_EDITOR"

echo "============================================"
echo "  All stacks deleted successfully! 🧹"
echo "============================================"
