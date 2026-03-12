#!/usr/bin/env bash
# -------------------------------------------------------------------
# synth.sh — Build and synthesize the LSS Workshop Platform CDK app,
#             then copy the CloudFormation template to the workshop
#             static assets directory.
#
# Usage:
#   cd Agent2Agent-Trivia-Night-Examples/platform/infrastructure
#   chmod +x synth.sh
#   ./synth.sh
#
# Prerequisites:
#   - Node.js and npm installed
#   - npm install already run in this directory
#   - npm install and npm run build already run in ../web-ui/
# -------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFN_OUTPUT_DIR="${SCRIPT_DIR}/../../../agent2agent-trivia-night/static/cfn"
TEMPLATE_NAME="chat-registry-platform.yaml"

echo "==> Step 1: Building TypeScript (tsc)..."
npm run build

echo "==> Step 2: Synthesizing CDK to CloudFormation..."
npx cdk synth --quiet

echo "==> Step 3: Copying synthesized template to workshop static assets..."
mkdir -p "${CFN_OUTPUT_DIR}"

# CDK synth outputs individual stack templates under cdk.out/
# We use the ApiStack template as the primary workshop template since
# the CDK app produces a multi-stack assembly. For a single-template
# deployment, merge or pick the relevant stack.
# Copy both stack templates for the workshop.
if [ -f "cdk.out/ApiStack.template.json" ]; then
  # Convert JSON to YAML if yq/cfn-flip is available, otherwise copy JSON
  if command -v cfn-flip &>/dev/null; then
    cfn-flip "cdk.out/ApiStack.template.json" "${CFN_OUTPUT_DIR}/${TEMPLATE_NAME}"
    echo "    Converted ApiStack template to YAML"
  else
    cp "cdk.out/ApiStack.template.json" "${CFN_OUTPUT_DIR}/chat-registry-api-stack.json"
    echo "    Copied ApiStack template (JSON)"
  fi
fi

if [ -f "cdk.out/WebUiStack.template.json" ]; then
  if command -v cfn-flip &>/dev/null; then
    cfn-flip "cdk.out/WebUiStack.template.json" "${CFN_OUTPUT_DIR}/chat-registry-webui-stack.yaml"
    echo "    Converted WebUiStack template to YAML"
  else
    cp "cdk.out/WebUiStack.template.json" "${CFN_OUTPUT_DIR}/chat-registry-webui-stack.json"
    echo "    Copied WebUiStack template (JSON)"
  fi
fi

echo ""
echo "==> Done! Templates are in: ${CFN_OUTPUT_DIR}"
echo ""
echo "Verify the templates include:"
echo "  - StackPrefix parameter (default: 'Workshop')"
echo "  - SSM parameter: /{StackPrefix}/platform/api-url"
echo "  - Outputs: CloudFront URL, API Gateway URL, Cognito console URL"
