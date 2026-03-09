"""
Test MCP server hosted on AgentCore Runtime using raw JSON-RPC over HTTP.
Fetches a Cognito M2M bearer token and uses it to authenticate requests.

Usage:
    python scripts/test_mcp_oauth.py [--pool-name CognitoUserPool] [--region us-east-1]
"""

import argparse
import base64
import json
import os
import sys
import urllib.request

import boto3
import httpx

AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:167428594774:runtime/AWSKnowledgeAgent_AWSKnowledgeAgent-BX0UHYDi7h"


# --- Token helpers ---

def get_ssm_param(ssm, path: str) -> str:
    return ssm.get_parameter(Name=path)["Parameter"]["Value"]


def get_m2m_client_secret(user_pool_id: str, client_id: str, region: str) -> str:
    cognito = boto3.client("cognito-idp", region_name=region)
    response = cognito.describe_user_pool_client(UserPoolId=user_pool_id, ClientId=client_id)
    return response["UserPoolClient"]["ClientSecret"]


def fetch_token(token_endpoint: str, client_id: str, client_secret: str) -> str:
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        token_endpoint,
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]


def get_bearer_token(pool_name: str, region: str) -> str:
    ssm = boto3.client("ssm", region_name=region)
    prefix = f"/{pool_name}/m2m"
    user_pool_id = get_ssm_param(ssm, f"{prefix}/user-pool-id")
    client_id = get_ssm_param(ssm, f"{prefix}/client-id")
    token_endpoint = get_ssm_param(ssm, f"{prefix}/token-endpoint")
    client_secret = get_m2m_client_secret(user_pool_id, client_id, region)
    return fetch_token(token_endpoint, client_id, client_secret)


# --- MCP client ---

def call_mcp(client: httpx.Client, url: str, method: str, params: dict = None):
    """Send a JSON-RPC MCP request and return the result."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = client.post(url, json=payload)
    response.raise_for_status()
    raw = response.text
    data = json.loads(raw[raw.find("{"):])
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")
    return data["result"]


def main():
    parser = argparse.ArgumentParser(description="Test AgentCore MCP server with OAuth")
    parser.add_argument("--pool-name", default="CognitoUserPool")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    args = parser.parse_args()

    print("=== Fetching Bearer Token ===")
    try:
        token = get_bearer_token(args.pool_name, args.region)
    except Exception as e:
        print(f"ERROR: Failed to fetch token: {e}", file=sys.stderr)
        sys.exit(1)
    print("Token acquired.\n")

    print(token)

    encoded_arn = AGENT_ARN.replace(":", "%3A").replace("/", "%2F")
    encoded_arn = "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A167428594774%3Aruntime%2FAWSKnowledgeAgent_AWSKnowledgeAgent-1x3TxP57lk"
    region = AGENT_ARN.split(":")[3]
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

    print(f"Connecting to: {mcp_url}\n")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    with httpx.Client(headers=headers, timeout=120) as client:
        # List tools
        print("=== Available Tools ===")
        tools_result = call_mcp(client, mcp_url, "tools/list")
        for tool in tools_result["tools"]:
            print(f"  {tool['name']}: {tool['description']}")
        print()

        # Call invoke tool
        print("invoke('Tell me about Bedrock AgentCore')")
        result = call_mcp(
            client,
            mcp_url,
            "tools/call",
            {"name": "invoke", "arguments": {"request": "Tell me about Bedrock AgentCore"}},
        )
        print(result["content"][0]["text"])


if __name__ == "__main__":
    main()
