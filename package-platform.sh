#!/usr/bin/env bash
# -------------------------------------------------------------------
# package-platform.sh — Package the platform directory into a zip
# for deployment via code-editor.yaml AssetZipS3Path.
#
# The zip is structured so that when extracted into the workshop
# HomeFolder (e.g. /workshop), the platform/ directory appears at
# the root: /workshop/platform/
#
# Usage:
#   chmod +x package-platform.sh
#   ./package-platform.sh
#
# Output:
#   ../agent2agent-trivia-night/static/platform.zip
# -------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$SCRIPT_DIR/platform"
OUTPUT_DIR="$SCRIPT_DIR/../agent2agent-trivia-night/assets"
OUTPUT_FILE="$OUTPUT_DIR/platform.zip"

echo "============================================"
echo "  Platform Packaging"
echo "============================================"
echo "  Source:  $PLATFORM_DIR"
echo "  Output:  $OUTPUT_FILE"
echo "============================================"
echo ""

# Verify source exists
if [ ! -d "$PLATFORM_DIR" ]; then
  echo "ERROR: Platform directory not found: $PLATFORM_DIR"
  exit 1
fi

# Create output directory if needed
mkdir -p "$OUTPUT_DIR"

# Remove old zip if it exists
if [ -f "$OUTPUT_FILE" ]; then
  echo "==> Removing existing zip..."
  rm -f "$OUTPUT_FILE"
fi

# Build the zip from the repo root so paths are relative
# e.g. platform/deploy.sh, platform/infrastructure/..., etc.
echo "==> Creating zip..."
cd "$SCRIPT_DIR"

zip -r "$OUTPUT_FILE" platform/ scripts/ \
  -x "scripts/__pycache__/*" \
  -x "platform/web-ui/node_modules/*" \
  -x "platform/web-ui/build/*" \
  -x "platform/web-ui/.vite/*" \
  -x "platform/infrastructure/node_modules/*" \
  -x "platform/infrastructure/cdk.out/*" \
  -x "platform/lambda/src/__pycache__/*" \
  -x "platform/lambda/src/*/__pycache__/*" \
  -x "platform/lambda/src/*/*/__pycache__/*" \
  -x "platform/lambda/src/*.dist-info/*" \
  -x "platform/lambda/src/*-*.dist-info/*" \
  -x "platform/lambda/src/boto3/*" \
  -x "platform/lambda/src/boto3-*/*" \
  -x "platform/lambda/src/botocore/*" \
  -x "platform/lambda/src/botocore-*/*" \
  -x "platform/lambda/src/s3transfer/*" \
  -x "platform/lambda/src/s3transfer-*/*" \
  -x "platform/lambda/src/jmespath/*" \
  -x "platform/lambda/src/jmespath-*/*" \
  -x "platform/lambda/src/dateutil/*" \
  -x "platform/lambda/src/python_dateutil-*/*" \
  -x "platform/lambda/src/six.py" \
  -x "platform/lambda/src/six-*/*" \
  -x "platform/lambda/src/urllib3/*" \
  -x "platform/lambda/src/urllib3-*/*" \
  -x "platform/lambda/src/certifi/*" \
  -x "platform/lambda/src/certifi-*/*" \
  -x "platform/lambda/src/charset_normalizer/*" \
  -x "platform/lambda/src/charset_normalizer-*/*" \
  -x "platform/lambda/src/idna/*" \
  -x "platform/lambda/src/idna-*/*" \
  -x "platform/lambda/src/requests/*" \
  -x "platform/lambda/src/requests-*/*" \
  -x "platform/lambda/src/mcp/*" \
  -x "platform/lambda/src/mcp-*/*" \
  -x "platform/lambda/src/httpx/*" \
  -x "platform/lambda/src/httpx-*/*" \
  -x "platform/lambda/src/httpx_sse/*" \
  -x "platform/lambda/src/httpx_sse-*/*" \
  -x "platform/lambda/src/httpcore/*" \
  -x "platform/lambda/src/httpcore-*/*" \
  -x "platform/lambda/src/h11/*" \
  -x "platform/lambda/src/h11-*/*" \
  -x "platform/lambda/src/anyio/*" \
  -x "platform/lambda/src/anyio-*/*" \
  -x "platform/lambda/src/sniffio/*" \
  -x "platform/lambda/src/sniffio-*/*" \
  -x "platform/lambda/src/click/*" \
  -x "platform/lambda/src/click-*/*" \
  -x "platform/lambda/src/starlette/*" \
  -x "platform/lambda/src/starlette-*/*" \
  -x "platform/lambda/src/uvicorn/*" \
  -x "platform/lambda/src/uvicorn-*/*" \
  -x "platform/lambda/src/sse_starlette/*" \
  -x "platform/lambda/src/sse_starlette-*/*" \
  -x "platform/lambda/src/pydantic/*" \
  -x "platform/lambda/src/pydantic-*/*" \
  -x "platform/lambda/src/pydantic_core/*" \
  -x "platform/lambda/src/pydantic_core-*/*" \
  -x "platform/lambda/src/pydantic_settings/*" \
  -x "platform/lambda/src/pydantic_settings-*/*" \
  -x "platform/lambda/src/annotated_types/*" \
  -x "platform/lambda/src/annotated_types-*/*" \
  -x "platform/lambda/src/typing_extensions*" \
  -x "platform/lambda/src/typing_inspection/*" \
  -x "platform/lambda/src/typing_inspection-*/*" \
  -x "platform/lambda/src/dotenv/*" \
  -x "platform/lambda/src/python_dotenv-*/*" \
  -x "platform/lambda/src/python_multipart/*" \
  -x "platform/lambda/src/python_multipart-*/*" \
  -x "platform/lambda/src/multipart/*" \
  -x "platform/lambda/src/cffi/*" \
  -x "platform/lambda/src/cffi-*/*" \
  -x "platform/lambda/src/cryptography/*" \
  -x "platform/lambda/src/cryptography-*/*" \
  -x "platform/lambda/src/pycparser/*" \
  -x "platform/lambda/src/pycparser-*/*" \
  -x "platform/lambda/src/jwt/*" \
  -x "platform/lambda/src/pyjwt-*/*" \
  -x "platform/lambda/src/attr/*" \
  -x "platform/lambda/src/attrs/*" \
  -x "platform/lambda/src/attrs-*/*" \
  -x "platform/lambda/src/referencing/*" \
  -x "platform/lambda/src/referencing-*/*" \
  -x "platform/lambda/src/rpds/*" \
  -x "platform/lambda/src/rpds_py-*/*" \
  -x "platform/lambda/src/jsonschema/*" \
  -x "platform/lambda/src/jsonschema-*/*" \
  -x "platform/lambda/src/jsonschema_specifications/*" \
  -x "platform/lambda/src/jsonschema_specifications-*/*" \
  -x "platform/lambda/src/packaging/*" \
  -x "platform/lambda/src/packaging-*/*" \
  -x "platform/lambda/src/pygments/*" \
  -x "platform/lambda/src/pygments-*/*" \
  -x "platform/lambda/src/coverage/*" \
  -x "platform/lambda/src/coverage-*/*" \
  -x "platform/lambda/src/hypothesis/*" \
  -x "platform/lambda/src/hypothesis-*/*" \
  -x "platform/lambda/src/sortedcontainers/*" \
  -x "platform/lambda/src/sortedcontainers-*/*" \
  -x "platform/lambda/src/pytest/*" \
  -x "platform/lambda/src/pytest-*/*" \
  -x "platform/lambda/src/pytest_cov/*" \
  -x "platform/lambda/src/pytest_cov-*/*" \
  -x "platform/lambda/src/_pytest/*" \
  -x "platform/lambda/src/pluggy/*" \
  -x "platform/lambda/src/pluggy-*/*" \
  -x "platform/lambda/src/iniconfig/*" \
  -x "platform/lambda/src/iniconfig-*/*" \
  -x "platform/lambda/src/bin/*" \
  -x "platform/lambda/src/*.so" \
  -x "platform/lambda/src/*.pth" \
  -x "platform/lambda/src/py.py" \
  -x "platform/lambda/src/_hypothesis_*" \
  -x "platform/lambda/src/81d*" \
  -x "**/.DS_Store" \
  -x "**/__pycache__/*"

echo ""
echo "============================================"
echo "  Package Complete"
echo "============================================"
ZIP_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo "  Output: $OUTPUT_FILE"
echo "  Size:   $ZIP_SIZE"
echo ""
echo "  Contents:"
echo "    platform/"
echo "    ├── deploy.sh"
echo "    ├── destroy.sh"
echo "    ├── infrastructure/  (CDK stacks)"
echo "    ├── lambda/          (API source code)"
echo "    └── web-ui/          (React app source)"
echo "    scripts/"
echo "    ├── deploy_and_register.py"
echo "    └── register_agent.py"
echo ""
echo "  Note: node_modules, build artifacts, and pip-installed"
echo "  dependencies are excluded. Run deploy.sh to install and build."
echo "============================================"
