"""
Test MCP server hosted on AgentCore Runtime using streamable HTTP transport.
Fetches a Cognito M2M bearer token and uses it to authenticate requests.

Usage:
    python scripts/test_mcp.py [--pool-name CognitoUserPool] [--region us-east-1]
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import urllib.request

import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from get_m2m_token import (
    get_ssm_param,
    get_m2m_client_secret,
    fetch_token,
    get_m2m_bearer_token,
)

AWS_KNOWLEDGE_AGENT_ARN = os.getenv("AWS_KNOWLEDGE_AGENT_ARN")


async def run(bearer_token: str):
    encoded_arn = AWS_KNOWLEDGE_AGENT_ARN.replace(":", "%3A").replace("/", "%2F")
    region = AWS_KNOWLEDGE_AGENT_ARN.split(":")[3]
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    headers = {
        "authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }

    print(f"Connecting to: {mcp_url}\n")

    async with streamablehttp_client(
        mcp_url, headers, timeout=120, terminate_on_close=False
    ) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # List tools
            print("=== Available Tools ===")
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                print(f"  {tool.name}: {tool.description}")
            print()

            # Call invoke tool
            print("invoke('Tell me about Bedrock AgentCore')")
            result = await session.call_tool(
                "invoke",
                {"request": "Tell me about Bedrock AgentCore"},
            )
            print(result.content[0].text)


def main():
    parser = argparse.ArgumentParser(description="Test AgentCore MCP server with OAuth")
    parser.add_argument("--pool-name", default="CognitoUserPool")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    args = parser.parse_args()

    print("=== Fetching Bearer Token ===")
    try:
        token = get_m2m_bearer_token(args.pool_name, args.region)
    except Exception as e:
        print(f"ERROR: Failed to fetch token: {e}", file=sys.stderr)
        sys.exit(1)
    print("Token acquired.\n")

    asyncio.run(run(token))


if __name__ == "__main__":
    main()
