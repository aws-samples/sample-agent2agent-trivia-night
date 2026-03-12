#!/usr/bin/env python3
"""
Agent Registration Seed Script

Registers the 4 adverse event agents in the A2A Agent Registry via the
deployed API Gateway endpoint using SigV4-signed requests.

Usage:
    python register_agents.py --api-url https://XXXXXXXXXX.execute-api.us-east-1.amazonaws.com
    python register_agents.py --api-url https://XXXXXXXXXX.execute-api.us-east-1.amazonaws.com --test-search
"""

import argparse
import json
import sys
from urllib.parse import urlencode, quote

import botocore.auth
import botocore.credentials
import botocore.session
from botocore.awsrequest import AWSRequest
import urllib3

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

AGENTS = [
    {
        "name": "Orchestrator Agent",
        "description": "Coordinates multi-agent adverse event investigation workflow",
        "url": "orchestrator-5G1XSk6aCt",
        "version": "1.0.0",
        "skills": [
            {"name": "coordinate_investigation", "description": "Coordinate multi-agent adverse event investigation workflow"},
            {"name": "list_agents", "description": "List all registered agents in the A2A registry"},
        ],
    },
    {
        "name": "Signal Detection Agent",
        "description": "Analyzes adverse event reports using statistical methods (PRR, ROR, IC025) to detect safety signals",
        "url": "adverse_event_signal_detection-Rb6ez2HHzC",
        "version": "1.0.0",
        "skills": [
            {"name": "analyze_events", "description": "Analyze adverse event reports for statistical signals using PRR, ROR, and IC025"},
            {"name": "calculate_disproportionality", "description": "Calculate disproportionality metrics for drug-event combinations"},
            {"name": "detect_signals", "description": "Detect safety signals from adverse event data"},
        ],
    },
    {
        "name": "Literature Mining Agent",
        "description": "Searches medical literature for drug safety evidence related to detected signals",
        "url": "adverse_event_literature_mining-JSgVgH7UsS",
        "version": "1.0.0",
        "skills": [
            {"name": "search_literature", "description": "Search medical literature for drug safety evidence"},
            {"name": "search_pubmed", "description": "Search PubMed for published research on adverse events"},
            {"name": "search_clinical_trials", "description": "Search clinical trial databases for safety data"},
        ],
    },
    {
        "name": "Regulatory Reporting Agent",
        "description": "Generates FDA MedWatch and EMA EudraVigilance regulatory safety reports",
        "url": "adverse_event_regulatory_reporting-N1CsONAkWX",
        "version": "1.0.0",
        "skills": [
            {"name": "generate_reports", "description": "Generate regulatory safety reports from investigation data"},
            {"name": "generate_medwatch", "description": "Generate FDA MedWatch (Form 3500A) reports"},
            {"name": "generate_eudravigilance", "description": "Generate EMA EudraVigilance ICSR reports"},
        ],
    },
]

SAMPLE_SEARCHES = [
    "analyze adverse events and detect statistical signals",
    "search medical literature for drug safety",
    "generate regulatory reports",
]

# ---------------------------------------------------------------------------
# SigV4-signed HTTP helpers
# ---------------------------------------------------------------------------


def _get_credentials():
    """Resolve AWS credentials from the default chain."""
    session = botocore.session.get_session()
    return session.get_credentials().get_frozen_credentials()


def _sigv4_request(method, url, body=None, region="us-east-1"):
    """Send an HTTP request signed with SigV4 for execute-api."""
    credentials = _get_credentials()

    headers = {"Content-Type": "application/json"}
    data = json.dumps(body) if body else ""

    aws_request = AWSRequest(method=method, url=url, data=data, headers=headers)
    signer = botocore.auth.SigV4Auth(credentials, "execute-api", region)
    signer.add_auth(aws_request)

    # Use the prepared request URL to ensure the URL sent matches what was signed
    signed_url = aws_request.url

    http = urllib3.PoolManager()
    resp = http.request(
        method,
        signed_url,
        body=data.encode("utf-8") if data else None,
        headers=dict(aws_request.headers),
    )
    return resp


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_agents(api_url, region="us-east-1"):
    """Register all agents via POST /agents and return list of agent_ids."""
    api_url = api_url.rstrip("/")
    endpoint = f"{api_url}/agents"

    registered = []
    for agent in AGENTS:
        print(f"Registering: {agent['name']} ...")
        resp = _sigv4_request("POST", endpoint, body=agent, region=region)
        status = resp.status
        body = json.loads(resp.data.decode("utf-8"))

        if status == 201:
            agent_id = body["agent_id"]
            registered.append(agent_id)
            print(f"  ✅ agent_id={agent_id}")
        else:
            print(f"  ❌ HTTP {status}: {body}")

    print()
    print(f"Registered {len(registered)}/{len(AGENTS)} agents")
    for aid in registered:
        print(f"  {aid}")

    return registered


# ---------------------------------------------------------------------------
# Test search
# ---------------------------------------------------------------------------


def test_search(api_url, region="us-east-1"):
    """Run sample semantic searches and print results."""
    api_url = api_url.rstrip("/")

    print()
    print("=" * 60)
    print("Running sample semantic searches")
    print("=" * 60)

    for query in SAMPLE_SEARCHES:
        params = urlencode({"query": query, "top_k": "3"}, quote_via=quote)
        url = f"{api_url}/agents/search?{params}"
        print(f"\nQuery: \"{query}\"")

        resp = _sigv4_request("GET", url, region=region)
        status = resp.status
        body = json.loads(resp.data.decode("utf-8"))

        if status == 200:
            results = body.get("results", [])
            if not results:
                print("  (no results)")
            for r in results:
                score = r.get("similarity_score", "n/a")
                print(f"  • {r['name']} (score={score})")
        else:
            print(f"  ❌ HTTP {status}: {body}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Seed the A2A Agent Registry with the 4 adverse event agents"
    )
    parser.add_argument(
        "--api-url",
        required=True,
        help="API Gateway endpoint URL (e.g. https://XXXXXXXXXX.execute-api.us-east-1.amazonaws.com)",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region for SigV4 signing (default: us-east-1)",
    )
    parser.add_argument(
        "--test-search",
        action="store_true",
        help="Run sample semantic searches after registration",
    )
    args = parser.parse_args()

    registered = register_agents(args.api_url, region=args.region)

    if args.test_search and registered:
        test_search(args.api_url, region=args.region)

    sys.exit(0 if len(registered) == len(AGENTS) else 1)


if __name__ == "__main__":
    main()
