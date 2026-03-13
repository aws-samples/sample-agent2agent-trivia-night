#!/usr/bin/env bash
# -------------------------------------------------------------------
# destroy.sh — Tear down the LSS Workshop Platform
#
# Destroys CDK stacks and cleans up SSM parameters for a given region.
#
# Usage:
#   chmod +x platform/destroy.sh
#   ./platform/destroy.sh --region eu-central-1
#   ./platform/destroy.sh --profile rbradaws-Admin --region eu-central-1
# -------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/infrastructure"

# Defaults
PROFILE=""
REGION="${AWS_REGION:-us-east-1}"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

PROFILE_FLAG=()
if [ -n "$PROFILE" ]; then
  PROFILE_FLAG=("--profile" "$PROFILE")
fi

export AWS_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"
export CDK_DEFAULT_REGION="$REGION"
export DEPLOY_REGION="$REGION"

API_STACK="ApiStack-${REGION}"
WEBUI_STACK="WebUiStack-${REGION}"

echo "============================================"
echo "  LSS Workshop Platform Destroy"
echo "============================================"
echo "  Profile: ${PROFILE:-<instance role>}"
echo "  Region:  $REGION"
echo "  Stacks:  $API_STACK, $WEBUI_STACK"
echo "============================================"
echo ""

# Verify credentials
echo "==> Verifying AWS credentials..."
CALLER_IDENTITY=$(aws sts get-caller-identity "${PROFILE_FLAG[@]}" --region "$REGION" --output json 2>&1) || {
  echo "ERROR: AWS authentication failed. Please check your authentication and try again."
  exit 1
}
export CDK_DEFAULT_ACCOUNT=$(echo "$CALLER_IDENTITY" | grep -o '"Account": "[^"]*"' | cut -d'"' -f4)
echo "    Credentials OK. Account: $CDK_DEFAULT_ACCOUNT"
echo ""

# Clean up SSM parameters
echo "==> Cleaning up SSM parameters..."
for param in /Workshop/platform/username /Workshop/platform/password /Workshop/platform/url /Workshop/platform/api-url; do
  aws ssm delete-parameter --name "$param" "${PROFILE_FLAG[@]}" --region "$REGION" > /dev/null 2>&1 || true
done
echo "    SSM parameters cleaned."
echo ""

# Destroy CDK stacks (WebUiStack first since it depends on ApiStack)
echo "==> Destroying CDK stacks..."
cd "$INFRA_DIR"

if [ ! -d "node_modules" ]; then
  echo "    Installing CDK dependencies..."
  npm install --silent
fi

npx cdk destroy "$WEBUI_STACK" "$API_STACK" "${PROFILE_FLAG[@]}" --region "$REGION" --force
echo ""

# Clean up credentials file
rm -f "$SCRIPT_DIR/workshop-credentials.txt"

echo "============================================"
echo "  Destroy Complete!"
echo "============================================"
echo "  Stacks $API_STACK and $WEBUI_STACK destroyed."
echo "============================================"
