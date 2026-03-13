#!/usr/bin/env python3
"""
Register a pre-deployed agent in the Agent Registry.

Standalone registration script for when the agent URL is already known
(e.g. the agent was deployed separately via ``agentcore launch``).

Usage:
    python scripts/register_agent.py \
        --name "MyAgent" \
        --description "Answers trivia about life sciences" \
        --url "https://runtime.bedrock-agentcore.us-east-1.amazonaws.com/..." \
        --skills "life-science,trivia"
"""

import argparse
import json
import os
import sys

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

DEFAULT_STACK_PREFIX = "Workshop"
DEFAULT_REGION = boto3.Session().region_name or "us-east-1"


# ---------------------------------------------------------------------------
# API URL discovery
# ---------------------------------------------------------------------------

def discover_api_url(region: str, stack_prefix: str, cli_api_url: str | None) -> str:
    """Return the registry API URL, trying multiple discovery methods.

    Order: CLI arg → env var → CloudFormation output → SSM parameter.
    """
    # 1. CLI argument (highest priority)
    if cli_api_url:
        print(f"Using API URL from --api-url: {cli_api_url}")
        return cli_api_url.rstrip("/")

    # 2. Environment variable
    env_url = os.environ.get("REGISTRY_API_URL")
    if env_url:
        print(f"Using API URL from REGISTRY_API_URL env var: {env_url}")
        return env_url.rstrip("/")

    # 3. CloudFormation stack output (ApiStack or ApiStack-{region})
    try:
        cfn = boto3.client("cloudformation", region_name=region)
        for stack_name in [f"ApiStack-{region}", "ApiStack"]:
            try:
                resp = cfn.describe_stacks(StackName=stack_name)
                for output in resp["Stacks"][0].get("Outputs", []):
                    if "ApiGatewayUrl" in output.get("OutputKey", ""):
                        value = output["OutputValue"]
                        print(f"Discovered API URL from CloudFormation {stack_name} output: {value}")
                        return value.rstrip("/")
            except Exception:
                continue
    except Exception:
        pass

    # 4. SSM Parameter Store
    ssm_param = f"/{stack_prefix}/platform/api-url"
    try:
        ssm = boto3.client("ssm", region_name=region)
        value = ssm.get_parameter(Name=ssm_param)["Parameter"]["Value"]
        print(f"Discovered API URL from SSM ({ssm_param}): {value}")
        return value.rstrip("/")
    except Exception:
        pass

    print("ERROR: Could not discover registry API URL.", file=sys.stderr)
    print("Tried: --api-url, REGISTRY_API_URL env, CloudFormation ApiStack output, SSM parameter.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Agent card construction
# ---------------------------------------------------------------------------

def build_agent_card(name: str, description: str, url: str, skills: list[str],
                     version: str = "1.0.0") -> dict:
    """Construct an A2A-compliant Agent_Card JSON payload per Google A2A spec."""
    card: dict = {
        "name": name,
        "description": description,
        "version": version,
        "url": url,
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "authentication": {
            "schemes": ["Bearer"],
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [],
    }
    if skills:
        card["skills"] = [
            {"id": s, "name": s, "description": s, "tags": [s.lower()]}
            for s in skills
        ]
    return card


# ---------------------------------------------------------------------------
# SigV4-signed registration
# ---------------------------------------------------------------------------

def register_agent(api_url: str, agent_card: dict, region: str) -> str:
    """POST the agent card to the registry with SigV4 signing.

    Returns the agent ID on success.  Prints error and exits on failure.
    """
    url = f"{api_url}/agents"
    body = json.dumps(agent_card)

    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    aws_request = AWSRequest(method="POST", url=url, data=body, headers={
        "Content-Type": "application/json",
    })
    SigV4Auth(credentials, "execute-api", region).add_auth(aws_request)

    response = requests.post(
        url,
        data=body,
        headers=dict(aws_request.headers),
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    return data.get("agent_id", data.get("agentId", "unknown"))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register a pre-deployed agent in the Agent Registry.",
    )
    parser.add_argument("--name", required=True, help="Agent display name")
    parser.add_argument("--description", required=True, help="Agent description")
    parser.add_argument("--url", default=None, help="Agent endpoint URL or AgentCore Runtime ARN")
    parser.add_argument("--arn", default=None, help="AgentCore Runtime ARN (alternative to --url)")
    parser.add_argument(
        "--skills",
        default="",
        help="Comma-separated list of skill names (optional)",
    )
    parser.add_argument("--version", default="1.0.0", help="Agent version (semver, default: 1.0.0)")
    parser.add_argument("--api-url", default=None, help="Registry API URL (overrides SSM / env)")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region")
    parser.add_argument(
        "--stack-prefix",
        default=DEFAULT_STACK_PREFIX,
        help="CloudFormation stack prefix for SSM lookup",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve URL: prefer --arn, fall back to --url
    agent_url = args.arn or args.url
    if not agent_url:
        print("ERROR: Either --url or --arn is required.", file=sys.stderr)
        sys.exit(1)

    # 1. Discover API URL
    api_url = discover_api_url(args.region, args.stack_prefix, args.api_url)

    # 2. Build agent card
    skills = [s.strip() for s in args.skills.split(",") if s.strip()]
    agent_card = build_agent_card(
        args.name, args.description, agent_url, skills,
        version=args.version,
    )

    # 3. Register
    print("Registering agent in the registry …")
    agent_id = register_agent(api_url, agent_card, args.region)

    print()
    print(f"Agent registered successfully!")
    print(f"  Agent ID: {agent_id}")
    print(f"  URL/ARN:  {agent_url}")


if __name__ == "__main__":
    main()
