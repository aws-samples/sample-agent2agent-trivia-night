#!/usr/bin/env python3
"""
Register an A2A agent in the Agent Registry using a pre-fetched agent card.

Usage:
    echo '<agent_card_json>' | python scripts/register_a2a.py
    python scripts/register_a2a.py --api-url "https://..."
"""

import argparse
import json
import os
import sys

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

DEFAULT_REGION = boto3.Session().region_name or "us-east-1"


def discover_api_url(cli_api_url: str | None, region: str) -> str:
    if cli_api_url:
        return cli_api_url.rstrip("/")
    env_url = os.environ.get("REGISTRY_API_URL")
    if env_url:
        return env_url.rstrip("/")
    print("ERROR: Registry API URL not found. Pass --api-url or set REGISTRY_API_URL.", file=sys.stderr)
    sys.exit(1)


def register_agent(api_url: str, agent_card: dict, region: str) -> str:
    url = f"{api_url}/agents"
    body = json.dumps(agent_card)

    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    aws_request = AWSRequest(method="POST", url=url, data=body, headers={
        "Content-Type": "application/json",
    })
    SigV4Auth(credentials, "execute-api", region).add_auth(aws_request)

    response = requests.post(url, data=body, headers=dict(aws_request.headers), timeout=30)
    response.raise_for_status()

    data = response.json()
    return data.get("agent_id", data.get("agentId", "unknown"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Register an A2A agent using a pre-fetched agent card.")
    parser.add_argument("--api-url", default=None, help="Registry API URL (overrides REGISTRY_API_URL env)")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region")
    args = parser.parse_args()

    agent_card = json.load(sys.stdin)

    api_url = discover_api_url(args.api_url, args.region)

    print("Registering agent in the registry...")
    agent_id = register_agent(api_url, agent_card, args.region)

    print(f"Agent registered successfully!")
    print(f"  Agent ID: {agent_id}")
    print(f"  Agent URL: {agent_card.get('url', 'N/A')}")


if __name__ == "__main__":
    main()
