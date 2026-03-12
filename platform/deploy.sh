#!/usr/bin/env bash
# -------------------------------------------------------------------
# deploy.sh — End-to-end deployment for the LSS Workshop Platform
#
# Deploys both the backend (ApiStack) and frontend (WebUiStack)
# including building the web UI, bundling Lambda code, and running
# CDK deploy.
#
# Usage:
#   chmod +x platform/deploy.sh
#   ./platform/deploy.sh
#
# Options:
#   --profile <name>   AWS profile (default: rbradaws-Admin)
#   --region <region>   AWS region (default: us-east-1)
#   --destroy          Tear down all stacks instead of deploying
#   --skip-build       Skip npm/pip install and build steps
#   --frontend-only    Deploy only the WebUiStack
#   --backend-only     Deploy only the ApiStack
# -------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$SCRIPT_DIR"
WEB_UI_DIR="$PLATFORM_DIR/web-ui"
LAMBDA_DIR="$PLATFORM_DIR/lambda"
INFRA_DIR="$PLATFORM_DIR/infrastructure"

# Defaults
PROFILE=""
REGION="${AWS_REGION:-us-east-1}"
DESTROY=false
SKIP_BUILD=false
FRONTEND_ONLY=false
BACKEND_ONLY=false

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile) PROFILE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --destroy) DESTROY=true; shift ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --frontend-only) FRONTEND_ONLY=true; shift ;;
    --backend-only) BACKEND_ONLY=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "============================================"
echo "  LSS Workshop Platform Deployment"
echo "============================================"
echo "  Profile: ${PROFILE:-<instance role>}"
echo "  Region:  $REGION"
echo "============================================"
echo ""

# Build profile flag (empty string if no profile specified)
PROFILE_FLAG=""
if [ -n "$PROFILE" ]; then
  PROFILE_FLAG="--profile $PROFILE"
fi

# Export region so CDK and AWS CLI always use the correct target region
export AWS_DEFAULT_REGION="$REGION"
export AWS_REGION="$REGION"
export CDK_DEFAULT_REGION="$REGION"
export DEPLOY_REGION="$REGION"

# -------------------------------------------------------------------
# Destroy mode
# -------------------------------------------------------------------
if [ "$DESTROY" = true ]; then
  echo "==> Destroying all stacks..."
  cd "$INFRA_DIR"
  npx cdk destroy --all $PROFILE_FLAG --region "$REGION" --force
  echo ""
  echo "==> All stacks destroyed."
  exit 0
fi

# -------------------------------------------------------------------
# Step 1: Verify AWS credentials
# -------------------------------------------------------------------
echo "==> Step 1: Verifying AWS credentials..."
CALLER_IDENTITY=$(aws sts get-caller-identity $PROFILE_FLAG --region "$REGION" --output json 2>&1) || {
  echo "ERROR: AWS authentication failed. Please check your authentication and try again."
  exit 1
}
export CDK_DEFAULT_ACCOUNT=$(echo "$CALLER_IDENTITY" | grep -o '"Account": "[^"]*"' | cut -d'"' -f4)
echo "    Credentials OK. Account: $CDK_DEFAULT_ACCOUNT, Region: $REGION"
echo ""

# -------------------------------------------------------------------
# Step 2: Install and build Web UI
# -------------------------------------------------------------------
if [ "$BACKEND_ONLY" = false ] && [ "$SKIP_BUILD" = false ]; then
  echo "==> Step 2: Building Web UI..."
  cd "$WEB_UI_DIR"

  if [ ! -d "node_modules" ]; then
    echo "    Installing npm dependencies..."
    npm install --silent
  fi

  echo "    Running TypeScript build + Vite bundle..."
  npm run build
  echo "    Web UI built to $WEB_UI_DIR/build/"
  echo ""
else
  echo "==> Step 2: Skipped (--backend-only or --skip-build)"
  echo ""
fi

# -------------------------------------------------------------------
# Step 3: Bundle Lambda dependencies
# -------------------------------------------------------------------
if [ "$FRONTEND_ONLY" = false ] && [ "$SKIP_BUILD" = false ]; then
  echo "==> Step 3: Bundling Lambda dependencies..."
  cd "$LAMBDA_DIR"

  # Install Python deps into src/ so they get bundled with Code.fromAsset
  pip install -q -r requirements.txt -t src/ 2>/dev/null || {
    echo "    WARNING: pip install failed. Lambda may be missing dependencies."
    echo "    Make sure boto3, requests, and mcp are available in the Lambda runtime."
  }
  echo "    Lambda dependencies bundled."
  echo ""
else
  echo "==> Step 3: Skipped (--frontend-only or --skip-build)"
  echo ""
fi

# -------------------------------------------------------------------
# Step 4: Install CDK dependencies
# -------------------------------------------------------------------
if [ "$SKIP_BUILD" = false ]; then
  echo "==> Step 4: Installing CDK dependencies..."
  cd "$INFRA_DIR"

  if [ ! -d "node_modules" ]; then
    echo "    Installing npm dependencies..."
    npm install --silent
  fi
  echo "    CDK dependencies ready."
  echo ""
else
  echo "==> Step 4: Skipped (--skip-build)"
  echo ""
fi

# -------------------------------------------------------------------
# Step 5: CDK Bootstrap (if needed)
# -------------------------------------------------------------------
echo "==> Step 5: Checking CDK bootstrap..."
cd "$INFRA_DIR"
# Bootstrap is idempotent — safe to run every time
npx cdk bootstrap $PROFILE_FLAG --region "$REGION" 2>/dev/null || {
  echo "    Bootstrap may have already been done. Continuing..."
}
echo ""

# -------------------------------------------------------------------
# Step 6: Deploy stacks
# -------------------------------------------------------------------
cd "$INFRA_DIR"

# Stack names include region suffix for multi-region support
API_STACK="ApiStack-${REGION}"
WEBUI_STACK="WebUiStack-${REGION}"

if [ "$FRONTEND_ONLY" = true ]; then
  echo "==> Step 6: Deploying $WEBUI_STACK only..."
  npx cdk deploy "$WEBUI_STACK" $PROFILE_FLAG --region "$REGION" --require-approval never
elif [ "$BACKEND_ONLY" = true ]; then
  echo "==> Step 6: Deploying $API_STACK only..."
  npx cdk deploy "$API_STACK" $PROFILE_FLAG --region "$REGION" --require-approval never
else
  echo "==> Step 6: Deploying all stacks..."
  npx cdk deploy --all $PROFILE_FLAG --region "$REGION" --require-approval never
fi

echo ""

# -------------------------------------------------------------------
# Step 7: Create Cognito user
# -------------------------------------------------------------------
if [ "$BACKEND_ONLY" != true ]; then
  echo "==> Step 7: Creating Cognito user..."

  USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name "$WEBUI_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue" \
    --output text \
    $PROFILE_FLAG --region "$REGION" 2>/dev/null || echo "")

  if [ -n "$USER_POOL_ID" ] && [ "$USER_POOL_ID" != "None" ]; then
    COGNITO_USERNAME="participant"
    COGNITO_PASSWORD=$(python3 -c "
import secrets, string
lower = string.ascii_lowercase
upper = string.ascii_uppercase
digits = string.digits
symbols = '!@#\$%^&*'
required = [secrets.choice(lower), secrets.choice(upper), secrets.choice(digits), secrets.choice(symbols)]
pool = lower + upper + digits + symbols
rest = [secrets.choice(pool) for _ in range(12)]
combined = required + rest
secrets.SystemRandom().shuffle(combined)
print(''.join(combined))
")

    # Create user (suppress if already exists)
    aws cognito-idp admin-create-user \
      --user-pool-id "$USER_POOL_ID" \
      --username "$COGNITO_USERNAME" \
      --user-attributes Name=email,Value=participant@workshop.local Name=given_name,Value=Workshop Name=family_name,Value=Participant Name=email_verified,Value=true \
      --message-action SUPPRESS \
      $PROFILE_FLAG --region "$REGION" > /dev/null 2>&1 || true

    # Set permanent password (no change required on login)
    aws cognito-idp admin-set-user-password \
      --user-pool-id "$USER_POOL_ID" \
      --username "$COGNITO_USERNAME" \
      --password "$COGNITO_PASSWORD" \
      --permanent \
      $PROFILE_FLAG --region "$REGION" > /dev/null

    echo "    User created: $COGNITO_USERNAME"

    # Write credentials to file for reference
    CREDS_FILE="$PLATFORM_DIR/workshop-credentials.txt"
    cat > "$CREDS_FILE" <<EOF
LSS Workshop Platform Credentials
==================================
Username: $COGNITO_USERNAME
Password: $COGNITO_PASSWORD
EOF
    echo "    Credentials saved to: $CREDS_FILE"

    # Write credentials and URLs to SSM for CloudFormation output retrieval
    CF_URL=$(aws cloudformation describe-stacks \
      --stack-name "$WEBUI_STACK" \
      --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
      --output text \
      $PROFILE_FLAG --region "$REGION" 2>/dev/null || echo "N/A")

    aws ssm put-parameter --name "/Workshop/platform/username" \
      --value "$COGNITO_USERNAME" --type String --overwrite \
      $PROFILE_FLAG --region "$REGION" > /dev/null 2>&1 || true
    aws ssm put-parameter --name "/Workshop/platform/password" \
      --value "$COGNITO_PASSWORD" --type SecureString --overwrite \
      $PROFILE_FLAG --region "$REGION" > /dev/null 2>&1 || true
    aws ssm put-parameter --name "/Workshop/platform/url" \
      --value "$CF_URL" --type String --overwrite \
      $PROFILE_FLAG --region "$REGION" > /dev/null 2>&1 || true
  else
    echo "    WARNING: Could not get User Pool ID. Skipping user creation."
    COGNITO_USERNAME="N/A"
    COGNITO_PASSWORD="N/A"
  fi
  echo ""
else
  echo "==> Step 7: Skipped (--backend-only)"
  echo ""
fi

# -------------------------------------------------------------------
# Step 8: Print outputs
# -------------------------------------------------------------------
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"
echo ""

# Fetch and display stack outputs
API_STACK="ApiStack-${REGION}"
WEBUI_STACK="WebUiStack-${REGION}"

if [ "$FRONTEND_ONLY" != true ]; then
  API_URL=$(aws cloudformation describe-stacks \
    --stack-name "$API_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" \
    --output text \
    $PROFILE_FLAG --region "$REGION" 2>/dev/null || echo "N/A")
  echo "  API Gateway URL:  $API_URL"
fi

if [ "$BACKEND_ONLY" != true ]; then
  CF_URL=$(aws cloudformation describe-stacks \
    --stack-name "$WEBUI_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontUrl'].OutputValue" \
    --output text \
    $PROFILE_FLAG --region "$REGION" 2>/dev/null || echo "N/A")
  COGNITO_URL=$(aws cloudformation describe-stacks \
    --stack-name "$WEBUI_STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolConsoleUrl'].OutputValue" \
    --output text \
    $PROFILE_FLAG --region "$REGION" 2>/dev/null || echo "N/A")
  echo "  CloudFront URL:   $CF_URL"
  echo "  Cognito Console:  $COGNITO_URL"
  if [ -n "${COGNITO_USERNAME:-}" ] && [ "$COGNITO_USERNAME" != "N/A" ]; then
    echo ""
    echo "  Login Credentials:"
    echo "    Username: $COGNITO_USERNAME"
    echo "    Password: $COGNITO_PASSWORD"
  fi
fi

echo ""
echo "  Next steps:"
echo "    1. Open the CloudFront URL in your browser"
echo "    2. Sign in with the credentials above"
echo ""
