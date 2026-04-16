#!/bin/bash
#
# deploy.sh — Deploy the Agent-to-Agent Trivia Night workshop into your own AWS account.
#
# Prerequisites:
#   - AWS CLI v2 installed and configured with credentials
#   - Sufficient IAM permissions to create the resources defined in the templates
#
# Usage:
#   ./scripts/deploy.sh                          # deploy to us-east-1 with defaults
#   ./scripts/deploy.sh us-west-2                # deploy to a specific region
#   ./scripts/deploy.sh us-east-1 MyPrefix       # deploy with a custom stack prefix
#
set -euo pipefail

REGION="${1:-us-east-1}"
STACK_PREFIX="${2:-Workshop}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/../infrastructure"

# Stack names derived from the prefix
STACK_CODE_EDITOR="${STACK_PREFIX}-CodeEditor"
STACK_AGENTCORE="${STACK_PREFIX}-AgentCorePolicies"
STACK_PLATFORM="${STACK_PREFIX}-Platform"
STACK_AGENTS="${STACK_PREFIX}-Agents"

CAPABILITIES="CAPABILITY_IAM CAPABILITY_NAMED_IAM CAPABILITY_AUTO_EXPAND"

# Resolve the AWS account ID for the S3 staging bucket name
ACCOUNT_ID=$(aws sts get-caller-identity --region "$REGION" --query Account --output text)
CFN_BUCKET="cfn-staging-${ACCOUNT_ID}-${REGION}"

echo "============================================"
echo "  Agent-to-Agent Trivia Night — Deployer"
echo "============================================"
echo "Region:       $REGION"
echo "Stack prefix: $STACK_PREFIX"
echo "CFN bucket:   $CFN_BUCKET"
echo ""

# Create the staging bucket if it doesn't already exist
if ! aws s3api head-bucket --bucket "$CFN_BUCKET" --region "$REGION" 2>/dev/null; then
  echo "Creating S3 staging bucket: $CFN_BUCKET"
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$CFN_BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$CFN_BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi
fi

deploy_stack() {
  local stack_name="$1"
  local template_file="$2"

  echo "--------------------------------------------"
  echo "Deploying: $stack_name"
  echo "Template:  $template_file"
  echo "--------------------------------------------"

  # Package the template (uploads large templates / local artifacts to S3)
  local packaged_template
  packaged_template=$(mktemp /tmp/cfn-packaged-XXXXXX.yaml)
  aws cloudformation package \
    --region "$REGION" \
    --template-file "$template_file" \
    --s3-bucket "$CFN_BUCKET" \
    --output-template-file "$packaged_template" > /dev/null

  aws cloudformation deploy \
    --region "$REGION" \
    --stack-name "$stack_name" \
    --template-file "$packaged_template" \
    --s3-bucket "$CFN_BUCKET" \
    --capabilities $CAPABILITIES \
    --no-fail-on-empty-changeset

  rm -f "$packaged_template"

  echo "✅ $stack_name deployed successfully."
  echo ""
}

# 1. Code Editor — sets up the EC2-based IDE and exports the bootstrap role name
deploy_stack "$STACK_CODE_EDITOR" "$INFRA_DIR/code-editor.yaml"

# 2. AgentCore Policies — attaches Bedrock AgentCore IAM policies to the Code Editor role
deploy_stack "$STACK_AGENTCORE" "$INFRA_DIR/agentcore-policies.yaml"

# 3. Platform — API backend, Web UI, Cognito, CodeBuild pipelines
deploy_stack "$STACK_PLATFORM" "$INFRA_DIR/platform.yaml"

# 4. Agents — CodeBuild project that deploys the A2A agents to AgentCore
deploy_stack "$STACK_AGENTS" "$INFRA_DIR/agents.yaml"

echo "============================================"
echo "  All stacks deployed successfully! 🎉"
echo "============================================"
echo ""

# Print useful outputs
echo "Key outputs:"
aws cloudformation describe-stacks \
  --region "$REGION" \
  --stack-name "$STACK_CODE_EDITOR" \
  --query "Stacks[0].Outputs[?OutputKey=='CodeEditorURL'].{Key:OutputKey,Value:OutputValue}" \
  --output table 2>/dev/null || true

aws cloudformation describe-stacks \
  --region "$REGION" \
  --stack-name "$STACK_PLATFORM" \
  --query "Stacks[0].Outputs[?OutputKey=='PlatformURL' || OutputKey=='PlatformUsername' || OutputKey=='PlatformPassword'].{Key:OutputKey,Value:OutputValue}" \
  --output table 2>/dev/null || true
