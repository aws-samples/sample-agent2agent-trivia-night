"""
Fetches a bearer token for the Cognito M2M client (client_credentials flow)
and prints it to stdout.

Usage:
    python scripts/get_token.py [--pool-name CognitoUserPool] [--region us-east-1]

Reads UserPoolId, M2MClientId, and TokenEndpoint from SSM Parameter Store
under /{pool-name}/m2m/*, then fetches the client secret from Cognito.
"""

import argparse
import base64
import json
import sys
import urllib.request

import boto3


def get_ssm_param(ssm, path: str) -> str:
    return ssm.get_parameter(Name=path)["Parameter"]["Value"]


def get_encrypted_ssm_param(ssm, path: str) -> str:
    return ssm.get_parameter(Name=path, WithDecryption=True)["Parameter"]["Value"]


def get_m2m_client_secret(user_pool_id: str, client_id: str, region: str) -> str:
    cognito = boto3.client("cognito-idp", region_name=region)
    response = cognito.describe_user_pool_client(
        UserPoolId=user_pool_id,
        ClientId=client_id,
    )
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
    with urllib.request.urlopen(req) as resp:  # nosec B310 — URL is constructed from a hardcoded HTTPS Cognito domain, not user input
        return json.loads(resp.read().decode())["access_token"]


def get_m2m_bearer_token(
    client_id: str, client_secret: str, user_pool_domain: str, region: str
) -> str:
    token_endpoint = (
        f"https://{user_pool_domain}.auth.{region}.amazoncognito.com/oauth2/token"
    )
    return fetch_token(token_endpoint, client_id, client_secret)


def main():
    parser = argparse.ArgumentParser(description="Get a Cognito M2M bearer token")
    parser.add_argument(
        "--pool-name", default="CognitoUserPool", help="Cognito pool name (SSM prefix)"
    )
    parser.add_argument(
        "--ssm-prefix",
        default="/Workshop/platform",
        help="SSM prefix (must start with /)",
    )
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()
    ssm = boto3.client("ssm", region_name=args.region)

    print("=== Fetching Parameters ===")

    try:
        client_id = get_ssm_param(ssm, f"{args.ssm_prefix}/m2m_client_id")
        client_secret = get_encrypted_ssm_param(
            ssm, f"{args.ssm_prefix}/m2m_client_secret"
        )
        discovery_url = get_ssm_param(ssm, f"{args.ssm_prefix}/cognito_discovery_url")
        user_pool_domain = get_ssm_param(ssm, f"{args.ssm_prefix}/user_pool_domain")
    except Exception as e:
        print(f"ERROR: Failed to read SSM parameters: {e}", file=sys.stderr)
        sys.exit(1)

    print("=== Fetching Bearer Token ===")
    try:
        token = get_m2m_bearer_token(
            client_id, client_secret, user_pool_domain, args.region
        )
    except Exception as e:
        print(f"ERROR: Failed to fetch token: {e}", file=sys.stderr)
        sys.exit(1)
    print("Token acquired.\n")

    print(f"Discovery URL:  {discovery_url}")
    print(f"Client ID:      {client_id}")
    print(f"Client Secret:  {client_secret}")
    print(f"Access Token:   {token}")


if __name__ == "__main__":
    main()
