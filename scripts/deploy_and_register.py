#!/usr/bin/env python3
"""
Deploy an agent to AgentCore and register it in the Agent Registry.

Wraps ``agentcore deploy`` + status polling + registry POST /agents into a
single command so workshop participants can deploy and register in one step.

Usage:
    cd agents/MyAgent
    python ../../scripts/deploy_and_register.py \\
        --name "MyAgent" \\
        --description "Answers trivia about life sciences" \\
        --skills "life-science,trivia"
"""

import argparse
import json
import os
import subprocess
import sys
import time

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

DEFAULT_STACK_PREFIX = "Workshop"
DEFAULT_REGION = boto3.Session().region_name or "us-east-1"
POLL_INTERVAL_SECONDS = 10
MAX_WAIT_SECONDS = 300  # 5 minutes


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
        # Try region-suffixed stack name first, then plain
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
# AgentCore launch & status polling
# ---------------------------------------------------------------------------

def run_agentcore_launch() -> None:
    """Run ``agentcore deploy`` to deploy the agent to AgentCore Runtime."""
    print("Deploying agent via agentcore …")
    result = subprocess.run(
        ["agentcore", "deploy"],
        capture_output=False,
    )
    if result.returncode != 0:
        print("ERROR: agentcore deploy failed.", file=sys.stderr)
        sys.exit(1)


def poll_until_ready() -> str:
    """Poll ``agentcore status`` or read ARN from config.

    Returns the agent ARN or endpoint URL.
    Falls back to reading the ARN from .bedrock_agentcore.yaml if
    agentcore status doesn't provide a parseable endpoint.
    """
    print("Waiting for endpoint to reach READY state …")
    deadline = time.time() + MAX_WAIT_SECONDS

    while time.time() < deadline:
        result = subprocess.run(
            ["agentcore", "status"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  agentcore status returned {result.returncode}, retrying …")
            time.sleep(POLL_INTERVAL_SECONDS) # nosemgrep
            continue

        output = result.stdout

        # Try JSON parse first
        status = {}
        try:
            status = json.loads(output)
            endpoint_url = extract_endpoint_url(status)
            if endpoint_url:
                print(f"Endpoint READY: {endpoint_url}")
                return endpoint_url
        except json.JSONDecodeError:
            pass

        # Try parsing text output for endpoint URL or ARN
        for line in output.splitlines():
            line = line.strip()
            # Look for ARN in output
            if "arn:aws:bedrock-agentcore:" in line:
                for word in line.split():
                    if word.startswith("arn:aws:bedrock-agentcore:"):
                        arn = word.rstrip(",;")
                        # Strip /runtime-endpoint/DEFAULT suffix if present
                        if "/runtime-endpoint/" in arn:
                            arn = arn.split("/runtime-endpoint/")[0]
                        print(f"Agent ARN found: {arn}")
                        return arn
            if "endpoint" in line.lower() and ("http://" in line or "https://" in line):
                for word in line.split():
                    if word.startswith("http://") or word.startswith("https://"):
                        url = word.rstrip(",;")
                        print(f"Endpoint found: {url}")
                        return url

        print("  Endpoint not ready yet, retrying …")
        time.sleep(POLL_INTERVAL_SECONDS) # nosemgrep

    # Fallback: try reading ARN from .bedrock_agentcore.yaml
    try:
        import yaml
        with open(".bedrock_agentcore.yaml") as f:
            config = yaml.safe_load(f)
        for agent_data in config.get("agents", {}).values():
            arn = (agent_data.get("bedrock_agentcore", {}) or {}).get("agent_arn")
            if arn:
                print(f"Using ARN from config: {arn}")
                return arn
    except Exception:
        pass

    print(
        f"ERROR: Endpoint did not reach READY state within {MAX_WAIT_SECONDS}s.",
        file=sys.stderr,
    )
    sys.exit(1)


def extract_endpoint_url(status: dict) -> str | None:
    """Extract the agent endpoint URL from agentcore status JSON.

    Looks for an endpoint entry whose status is ``READY`` and returns its URL.
    Returns ``None`` if no ready endpoint is found.
    """
    # Handle both flat and nested status shapes
    endpoints = status.get("endpoints", [])
    if isinstance(endpoints, list):
        for ep in endpoints:
            if isinstance(ep, dict) and ep.get("status") == "READY":
                return ep.get("url") or ep.get("endpoint_url")

    # Flat shape: top-level status + url
    if status.get("status") == "READY":
        return status.get("url") or status.get("endpoint_url")

    return None


# ---------------------------------------------------------------------------
# Registry registration (SigV4-signed POST /agents)
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


def register_agent(api_url: str, agent_card: dict, region: str) -> str:
    """POST the agent card to the registry with SigV4 signing.

    Returns the agent ID on success.  Prints error and exits on failure.
    """
    url = f"{api_url}/agents"
    body = json.dumps(agent_card)

    # Build and sign the request
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

    if response.status_code >= 400:
        print(
            f"ERROR: Registration failed (HTTP {response.status_code}): {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    data = response.json()
    return data.get("agent_id", data.get("agentId", "unknown"))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy an agent to AgentCore and register it in the Agent Registry.",
    )
    parser.add_argument("--name", required=True, help="Agent display name")
    parser.add_argument("--description", required=True, help="Agent description")
    parser.add_argument(
        "--skills",
        default="",
        help="Comma-separated list of skill names (optional)",
    )
    parser.add_argument("--arn", default=None, help="AgentCore Runtime ARN (skip deploy, register only)")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip agentcore deploy step")
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

    # 1. Discover API URL
    api_url = discover_api_url(args.region, args.stack_prefix, args.api_url)

    if args.arn:
        # Skip deploy and poll — use the provided ARN directly
        endpoint_url = args.arn
        print(f"Using provided ARN: {endpoint_url}")
    else:
        # 2. Launch agent
        if not args.skip_deploy:
            run_agentcore_launch()

        # 3. Poll until endpoint is ready
        endpoint_url = poll_until_ready()

    # 4. Build agent card
    skills = [s.strip() for s in args.skills.split(",") if s.strip()]
    agent_card = build_agent_card(
        args.name, args.description, endpoint_url, skills,
        version=args.version,
    )

    # 5. Register
    print("Registering agent in the registry …")
    agent_id = register_agent(api_url, agent_card, args.region)

    print()
    print(f"Agent registered successfully!")
    print(f"  Agent ID:     {agent_id}")
    print(f"  Endpoint URL: {endpoint_url}")


if __name__ == "__main__":
    main()
