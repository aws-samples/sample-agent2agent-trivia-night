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
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())["access_token"]


def main():
    parser = argparse.ArgumentParser(description="Get a Cognito M2M bearer token")
    parser.add_argument("--pool-name", default="CognitoUserPool", help="Cognito pool name (SSM prefix)")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    args = parser.parse_args()

    ssm = boto3.client("ssm", region_name=args.region)
    prefix = f"/{args.pool_name}/m2m"

    try:
        user_pool_id = get_ssm_param(ssm, f"{prefix}/user-pool-id")
        client_id = get_ssm_param(ssm, f"{prefix}/client-id")
        token_endpoint = get_ssm_param(ssm, f"{prefix}/token-endpoint")
    except Exception as e:
        print(f"ERROR: Failed to read SSM parameters: {e}", file=sys.stderr)
        sys.exit(1)

    client_secret = get_m2m_client_secret(user_pool_id, client_id, args.region)
    discovery_url = f"https://cognito-idp.{args.region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"
    access_token = fetch_token(token_endpoint, client_id, client_secret)

    print(f"Discovery URL:  {discovery_url}")
    print(f"Token URL:      {token_endpoint}")
    print(f"Client ID:      {client_id}")
    print(f"Client Secret:  {client_secret}")
    print(f"Access Token:   {access_token}")


if __name__ == "__main__":
    main()
