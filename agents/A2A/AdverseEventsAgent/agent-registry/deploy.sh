#!/usr/bin/env bash
# =============================================================================
# A2A Agent Registry — Infrastructure Deployment Script
#
# Provisions: DynamoDB table, S3 Vectors bucket+index, IAM role, Lambda
# function, and API Gateway HTTP API with IAM auth.
#
# Idempotent — safe to re-run; skips resources that already exist.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REGION="us-east-1"
ACCOUNT_ID="730763206378"

# DynamoDB
TABLE_NAME="A2AAgentRegistry"

# S3 Vectors
S3V_BUCKET="a2a-agent-registry-vectors-${ACCOUNT_ID}"
S3V_INDEX="agent-embeddings"

# IAM
ROLE_NAME="A2AAgentRegistryLambdaRole"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# Lambda
FUNCTION_NAME="A2AAgentRegistryHandler"
RUNTIME="python3.12"
HANDLER="handler.handler"
MEMORY=512
TIMEOUT=30
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# API Gateway
API_NAME="A2AAgentRegistryAPI"

echo "============================================="
echo " A2A Agent Registry — Deploying to ${REGION}"
echo "============================================="

# =====================================================================
# 1. DynamoDB Table
# =====================================================================
echo ""
echo "--- 1. DynamoDB Table: ${TABLE_NAME} ---"

if aws dynamodb describe-table --table-name "${TABLE_NAME}" --region "${REGION}" >/dev/null 2>&1; then
    echo "Table '${TABLE_NAME}' already exists — skipping."
else
    echo "Creating DynamoDB table '${TABLE_NAME}'..."
    aws dynamodb create-table \
        --table-name "${TABLE_NAME}" \
        --attribute-definitions AttributeName=agent_id,AttributeType=S \
        --key-schema AttributeName=agent_id,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "${REGION}"

    echo "Waiting for table to become ACTIVE..."
    aws dynamodb wait table-exists --table-name "${TABLE_NAME}" --region "${REGION}"
    echo "Table '${TABLE_NAME}' is ACTIVE."
fi

# =====================================================================
# 2. S3 Vectors — Bucket + Index (via Python/boto3 to avoid CLI version issues)
# =====================================================================
echo ""
echo "--- 2. S3 Vectors: ${S3V_BUCKET} / ${S3V_INDEX} ---"

python3 - "${S3V_BUCKET}" "${S3V_INDEX}" "${REGION}" <<'PYEOF'
import sys, boto3
from botocore.exceptions import ClientError

bucket_name, index_name, region = sys.argv[1], sys.argv[2], sys.argv[3]

try:
    client = boto3.client("s3vectors", region_name=region)
except Exception:
    print("ERROR: boto3 does not support s3vectors. Upgrade with: pip install --upgrade boto3 botocore")
    sys.exit(1)

# 2a. Create vector bucket (idempotent)
try:
    buckets = client.list_vector_buckets().get("vectorBuckets", [])
    if any(b["vectorBucketName"] == bucket_name for b in buckets):
        print(f"Vector bucket '{bucket_name}' already exists — skipping.")
    else:
        print(f"Creating S3 Vectors bucket '{bucket_name}'...")
        client.create_vector_bucket(vectorBucketName=bucket_name)
        print("Vector bucket created.")
except ClientError as e:
    print(f"Error with vector bucket: {e}")
    sys.exit(1)

# 2b. Create vector index (idempotent)
try:
    indexes = client.list_indexes(vectorBucketName=bucket_name).get("indexes", [])
    if any(i["indexName"] == index_name for i in indexes):
        print(f"Vector index '{index_name}' already exists — skipping.")
    else:
        print(f"Creating S3 Vectors index '{index_name}' (1024 dims, cosine)...")
        client.create_index(
            vectorBucketName=bucket_name,
            indexName=index_name,
            dataType="float32",
            dimension=1024,
            distanceMetric="cosine",
        )
        print("Vector index created.")
except ClientError as e:
    print(f"Error with vector index: {e}")
    sys.exit(1)
PYEOF

if [ $? -ne 0 ]; then
    echo "❌ S3 Vectors setup failed. Ensure boto3 is up to date: pip install --upgrade boto3"
    exit 1
fi

# =====================================================================
# 3. IAM Execution Role for Lambda
# =====================================================================
echo ""
echo "--- 3. IAM Role: ${ROLE_NAME} ---"

TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}'

INLINE_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:'"${REGION}"':'"${ACCOUNT_ID}"':table/'"${TABLE_NAME}"'"
    },
    {
      "Sid": "S3VectorsAccess",
      "Effect": "Allow",
      "Action": [
        "s3vectors:PutVectors",
        "s3vectors:QueryVectors",
        "s3vectors:GetVectors",
        "s3vectors:DeleteVectors"
      ],
      "Resource": [
        "arn:aws:s3vectors:'"${REGION}"':'"${ACCOUNT_ID}"':bucket/'"${S3V_BUCKET}"'",
        "arn:aws:s3vectors:'"${REGION}"':'"${ACCOUNT_ID}"':bucket/'"${S3V_BUCKET}"'/index/'"${S3V_INDEX}"'"
      ]
    },
    {
      "Sid": "BedrockInvokeModel",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:'"${REGION}"'::foundation-model/amazon.titan-embed-text-v2:0"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:'"${REGION}"':'"${ACCOUNT_ID}"':*"
    }
  ]
}'

if aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
    echo "IAM role '${ROLE_NAME}' already exists — skipping creation."
    echo "Updating inline policy..."
    aws iam put-role-policy \
        --role-name "${ROLE_NAME}" \
        --policy-name "A2AAgentRegistryPolicy" \
        --policy-document "${INLINE_POLICY}"
    echo "Inline policy updated."
else
    echo "Creating IAM role '${ROLE_NAME}'..."
    aws iam create-role \
        --role-name "${ROLE_NAME}" \
        --assume-role-policy-document "${TRUST_POLICY}" \
        --description "Execution role for A2A Agent Registry Lambda"

    echo "Attaching inline policy..."
    aws iam put-role-policy \
        --role-name "${ROLE_NAME}" \
        --policy-name "A2AAgentRegistryPolicy" \
        --policy-document "${INLINE_POLICY}"

    echo "Waiting 10s for IAM role propagation..."
    sleep 10
fi

ROLE_ARN="$(aws iam get-role --role-name "${ROLE_NAME}" --query 'Role.Arn' --output text)"
echo "Role ARN: ${ROLE_ARN}"

# =====================================================================
# 4. Lambda Function
# =====================================================================
echo ""
echo "--- 4. Lambda Function: ${FUNCTION_NAME} ---"

# Package handler
echo "Packaging Lambda code..."
ZIPFILE="/tmp/a2a-agent-registry-lambda.zip"
(cd "${SCRIPT_DIR}" && zip -j "${ZIPFILE}" handler.py)

if aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${REGION}" >/dev/null 2>&1; then
    echo "Lambda function '${FUNCTION_NAME}' already exists — updating code and configuration..."
    aws lambda update-function-code \
        --function-name "${FUNCTION_NAME}" \
        --zip-file "fileb://${ZIPFILE}" \
        --region "${REGION}" >/dev/null

    # Wait for the update to complete before changing configuration
    aws lambda wait function-updated --function-name "${FUNCTION_NAME}" --region "${REGION}"

    aws lambda update-function-configuration \
        --function-name "${FUNCTION_NAME}" \
        --runtime "${RUNTIME}" \
        --handler "${HANDLER}" \
        --memory-size "${MEMORY}" \
        --timeout "${TIMEOUT}" \
        --role "${ROLE_ARN}" \
        --environment "Variables={TABLE_NAME=${TABLE_NAME},S3_VECTORS_BUCKET=${S3V_BUCKET},S3_VECTORS_INDEX=${S3V_INDEX}}" \
        --region "${REGION}" >/dev/null

    echo "Lambda function updated."
else
    echo "Creating Lambda function '${FUNCTION_NAME}'..."
    aws lambda create-function \
        --function-name "${FUNCTION_NAME}" \
        --runtime "${RUNTIME}" \
        --handler "${HANDLER}" \
        --memory-size "${MEMORY}" \
        --timeout "${TIMEOUT}" \
        --role "${ROLE_ARN}" \
        --zip-file "fileb://${ZIPFILE}" \
        --environment "Variables={TABLE_NAME=${TABLE_NAME},S3_VECTORS_BUCKET=${S3V_BUCKET},S3_VECTORS_INDEX=${S3V_INDEX}}" \
        --region "${REGION}" >/dev/null

    echo "Waiting for Lambda to become Active..."
    aws lambda wait function-active --function-name "${FUNCTION_NAME}" --region "${REGION}"
    echo "Lambda function created."
fi

LAMBDA_ARN="$(aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${REGION}" \
    --query 'Configuration.FunctionArn' --output text)"
echo "Lambda ARN: ${LAMBDA_ARN}"

# Clean up zip
rm -f "${ZIPFILE}"

# =====================================================================
# 5. API Gateway HTTP API
# =====================================================================
echo ""
echo "--- 5. API Gateway HTTP API: ${API_NAME} ---"

# Check if API already exists
API_ID="$(aws apigatewayv2 get-apis --region "${REGION}" \
    --query "Items[?Name=='${API_NAME}'].ApiId | [0]" --output text 2>/dev/null || true)"

if [ -n "${API_ID}" ] && [ "${API_ID}" != "None" ]; then
    echo "API '${API_NAME}' already exists (ID: ${API_ID}) — skipping creation."
else
    echo "Creating HTTP API '${API_NAME}'..."
    API_ID="$(aws apigatewayv2 create-api \
        --name "${API_NAME}" \
        --protocol-type HTTP \
        --region "${REGION}" \
        --query 'ApiId' --output text)"
    echo "API created (ID: ${API_ID})."

    # --- Lambda Integration ---
    echo "Creating Lambda proxy integration..."
    INTEGRATION_ID="$(aws apigatewayv2 create-integration \
        --api-id "${API_ID}" \
        --integration-type AWS_PROXY \
        --integration-uri "${LAMBDA_ARN}" \
        --payload-format-version "2.0" \
        --region "${REGION}" \
        --query 'IntegrationId' --output text)"
    echo "Integration created (ID: ${INTEGRATION_ID})."

    # --- Grant API Gateway permission to invoke Lambda ---
    echo "Adding Lambda invoke permission for API Gateway..."
    aws lambda add-permission \
        --function-name "${FUNCTION_NAME}" \
        --statement-id "apigateway-invoke-${API_ID}" \
        --action "lambda:InvokeFunction" \
        --principal "apigateway.amazonaws.com" \
        --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT_ID}:${API_ID}/*" \
        --region "${REGION}" >/dev/null 2>&1 || echo "  (permission already exists)"

    # --- Routes ---
    TARGET="integrations/${INTEGRATION_ID}"

    declare -a ROUTES=(
        "POST /agents"
        "GET /agents"
        "GET /agents/search"
        "GET /agents/{id}"
        "PUT /agents/{id}"
        "DELETE /agents/{id}"
        "POST /agents/{id}/health"
    )

    echo "Creating routes..."
    for ROUTE in "${ROUTES[@]}"; do
        echo "  → ${ROUTE}"
        aws apigatewayv2 create-route \
            --api-id "${API_ID}" \
            --route-key "${ROUTE}" \
            --target "${TARGET}" \
            --authorization-type AWS_IAM \
            --region "${REGION}" >/dev/null
    done
    echo "All routes created."

    # --- Auto-deploy stage ---
    echo "Creating \$default stage with auto-deploy..."
    aws apigatewayv2 create-stage \
        --api-id "${API_ID}" \
        --stage-name '$default' \
        --auto-deploy \
        --region "${REGION}" >/dev/null
    echo "Stage created."
fi

# =====================================================================
# 6. Output
# =====================================================================
API_ENDPOINT="$(aws apigatewayv2 get-api --api-id "${API_ID}" --region "${REGION}" \
    --query 'ApiEndpoint' --output text)"

echo ""
echo "============================================="
echo " Deployment Complete!"
echo "============================================="
echo ""
echo " API Endpoint : ${API_ENDPOINT}"
echo " DynamoDB Table : ${TABLE_NAME}"
echo " S3 Vectors Bucket: ${S3V_BUCKET}"
echo " S3 Vectors Index : ${S3V_INDEX}"
echo " Lambda Function : ${FUNCTION_NAME}"
echo " Region          : ${REGION}"
echo ""
echo " All endpoints require IAM SigV4 authentication."
echo "============================================="
