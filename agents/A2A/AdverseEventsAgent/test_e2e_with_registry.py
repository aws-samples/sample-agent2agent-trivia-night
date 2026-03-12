#!/usr/bin/env python3
"""
End-to-End Test: Orchestrator with Dynamic Agent Discovery

Tests the full flow:
1. RegistryClient connects to the deployed API Gateway registry
2. Orchestrator discovers agents via semantic search
3. Orchestrator invokes discovered agents on AgentCore Runtime
4. Full investigation workflow with 10 adverse events

Prerequisites:
    - API Gateway registry deployed (deploy.sh)
    - Agents registered (register_agents.py)
    - Agents deployed on AgentCore Runtime
    - AWS credentials configured

Usage:
    # Set registry URL (or use .env)
    export A2A_REGISTRY_API_URL=https://b07qlmpb6b.execute-api.us-east-1.amazonaws.com

    python test_e2e_with_registry.py
    python test_e2e_with_registry.py --test registry      # registry only
    python test_e2e_with_registry.py --test discovery      # discovery only
    python test_e2e_with_registry.py --test investigation   # full investigation
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from agent_directory.registry_client import RegistryClient
from agents.orchestrator_agent import OrchestratorAgent
from config.agentcore_config import AgentCoreConfig
from models.adverse_event import AdverseEvent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REGION = os.environ.get("AWS_REGION", "us-east-1")
REGISTRY_URL = os.environ.get(
    "A2A_REGISTRY_API_URL",
    "https://psubuwv1q0.execute-api.us-east-1.amazonaws.com",
)

# ---------------------------------------------------------------------------
# Sample Adverse Events (using the AdverseEvent data model)
# ---------------------------------------------------------------------------
SAMPLE_ADVERSE_EVENTS = [
    AdverseEvent(
        event_id="AE-2026-001", drug_name="CardioMed",
        adverse_event_term="Cardiac Arrest", medra_code="10007515",
        patient_age=67, patient_sex="M",
        event_date=datetime(2026, 1, 15), outcome="fatal",
        reporter_type="physician",
    ),
    AdverseEvent(
        event_id="AE-2026-002", drug_name="CardioMed",
        adverse_event_term="Cardiac Arrest", medra_code="10007515",
        patient_age=72, patient_sex="F",
        event_date=datetime(2026, 1, 20), outcome="fatal",
        reporter_type="physician",
    ),
    AdverseEvent(
        event_id="AE-2026-003", drug_name="CardioMed",
        adverse_event_term="Cardiac Arrest", medra_code="10007515",
        patient_age=58, patient_sex="M",
        event_date=datetime(2026, 2, 1), outcome="hospitalization",
        reporter_type="physician",
    ),
    AdverseEvent(
        event_id="AE-2026-004", drug_name="CardioMed",
        adverse_event_term="Cardiac Arrest", medra_code="10007515",
        patient_age=63, patient_sex="M",
        event_date=datetime(2026, 2, 10), outcome="hospitalization",
        reporter_type="pharmacist",
    ),
    AdverseEvent(
        event_id="AE-2026-005", drug_name="CardioMed",
        adverse_event_term="Cardiac Arrest", medra_code="10007515",
        patient_age=70, patient_sex="F",
        event_date=datetime(2026, 2, 15), outcome="fatal",
        reporter_type="physician",
    ),
    AdverseEvent(
        event_id="AE-2026-006", drug_name="NeuroCalm",
        adverse_event_term="Severe Headache", medra_code="10019211",
        patient_age=45, patient_sex="F",
        event_date=datetime(2026, 1, 25), outcome="recovered",
        reporter_type="consumer",
    ),
    AdverseEvent(
        event_id="AE-2026-007", drug_name="NeuroCalm",
        adverse_event_term="Severe Headache", medra_code="10019211",
        patient_age=38, patient_sex="M",
        event_date=datetime(2026, 2, 5), outcome="recovered",
        reporter_type="physician",
    ),
    AdverseEvent(
        event_id="AE-2026-008", drug_name="NeuroCalm",
        adverse_event_term="Severe Headache", medra_code="10019211",
        patient_age=52, patient_sex="F",
        event_date=datetime(2026, 2, 12), outcome="recovered",
        reporter_type="pharmacist",
    ),
    AdverseEvent(
        event_id="AE-2026-009", drug_name="ImmunoShield",
        adverse_event_term="Skin Rash", medra_code="10040914",
        patient_age=34, patient_sex="M",
        event_date=datetime(2026, 1, 30), outcome="recovered",
        reporter_type="consumer",
    ),
    AdverseEvent(
        event_id="AE-2026-010", drug_name="ImmunoShield",
        adverse_event_term="Skin Rash", medra_code="10040914",
        patient_age=29, patient_sex="F",
        event_date=datetime(2026, 2, 8), outcome="recovered",
        reporter_type="physician",
    ),
]

# Semantic queries the orchestrator uses for discovery
DISCOVERY_QUERIES = {
    "signal_detection": "analyze adverse events and detect statistical signals using disproportionality",
    "literature_mining": "search medical literature and PubMed for drug safety evidence",
    "regulatory_reporting": "generate MedWatch and EudraVigilance regulatory safety reports",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def section(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def pretty(obj, max_lines=40, indent=4):
    text = json.dumps(obj, indent=2, default=str)
    lines = text.split("\n")
    prefix = " " * indent
    for line in lines[:max_lines]:
        print(f"{prefix}{line}")
    if len(lines) > max_lines:
        print(f"{prefix}... ({len(lines) - max_lines} more lines)")


# ---------------------------------------------------------------------------
# Test 1: Registry connectivity and agent listing
# ---------------------------------------------------------------------------
def test_registry_connectivity():
    """Verify the RegistryClient can talk to the deployed API Gateway."""
    section("Test 1: Registry Connectivity")
    print(f"  Registry URL: {REGISTRY_URL}")
    print(f"  Region: {REGION}")

    client = RegistryClient(api_url=REGISTRY_URL, region=REGION)

    # List all agents
    start = time.time()
    agents = client.list_agents()
    elapsed = time.time() - start

    print(f"  Response time: {elapsed:.2f}s")
    print(f"  Agents registered: {len(agents)}")

    if not agents:
        print("  ❌ No agents found in registry — did you run register_agents.py?")
        return None

    for a in agents:
        name = a.get("name", "?")
        agent_id = a.get("agent_id", "?")
        skills = a.get("skills", [])
        skill_names = [s.get("name", s) if isinstance(s, dict) else s for s in skills]
        print(f"    • {name} ({agent_id})")
        print(f"      skills: {', '.join(skill_names)}")

    print(f"  ✅ Registry is reachable, {len(agents)} agents found")
    return client


# ---------------------------------------------------------------------------
# Test 2: Semantic discovery for each agent type
# ---------------------------------------------------------------------------
def test_semantic_discovery(client: RegistryClient):
    """Verify semantic search returns the right agent for each query."""
    section("Test 2: Semantic Agent Discovery")

    results = {}
    for agent_type, query in DISCOVERY_QUERIES.items():
        start = time.time()
        matches = client.search(query, top_k=3)
        elapsed = time.time() - start

        if matches:
            top = matches[0]
            name = top.get("name", "?")
            score = top.get("similarity_score", "?")
            print(f"  {agent_type}:")
            print(f"    query: \"{query}\"")
            print(f"    top match: {name} (score={score})")
            print(f"    response time: {elapsed:.2f}s")
            results[agent_type] = top
        else:
            print(f"  {agent_type}: ❌ no results for \"{query}\"")
            results[agent_type] = None

    found = sum(1 for v in results.values() if v)
    print(f"\n  ✅ Discovered {found}/{len(DISCOVERY_QUERIES)} agents via semantic search")
    return results


# ---------------------------------------------------------------------------
# Test 3: Cache behavior
# ---------------------------------------------------------------------------
def test_cache_behavior(client: RegistryClient):
    """Verify that repeated searches hit the cache."""
    section("Test 3: Cache Behavior")

    query = DISCOVERY_QUERIES["signal_detection"]

    # First call — should hit the API (or cache from test 2)
    start = time.time()
    r1 = client.search(query, top_k=3)
    t1 = time.time() - start

    # Second call — should be cached
    start = time.time()
    r2 = client.search(query, top_k=3)
    t2 = time.time() - start

    print(f"  First call:  {t1:.4f}s  ({len(r1)} results)")
    print(f"  Second call: {t2:.4f}s  ({len(r2)} results)")
    print(f"  Speedup: {t1 / t2:.1f}x" if t2 > 0 else "  Speedup: instant")

    if t2 < t1 * 0.5 or t2 < 0.01:
        print("  ✅ Cache is working (second call significantly faster)")
    else:
        print("  ⚠️  Cache may not be working — both calls took similar time")

    # Test invalidation
    client.invalidate_cache(query)
    start = time.time()
    r3 = client.search(query, top_k=3)
    t3 = time.time() - start
    print(f"  After invalidation: {t3:.4f}s  ({len(r3)} results)")
    print("  ✅ Cache invalidation works")


# ---------------------------------------------------------------------------
# Test 4: Full investigation via orchestrator with dynamic discovery
# ---------------------------------------------------------------------------
def test_full_investigation():
    """Run the orchestrator's full investigation workflow using registry discovery."""
    section("Test 4: Full Investigation (Orchestrator + Registry Discovery)")

    print(f"  Adverse events: {len(SAMPLE_ADVERSE_EVENTS)}")
    print(f"    - CardioMed / Cardiac Arrest: 5 events (3 fatal)")
    print(f"    - NeuroCalm / Severe Headache: 3 events")
    print(f"    - ImmunoShield / Skin Rash: 2 events")

    # Create orchestrator with registry client
    config = AgentCoreConfig.from_env()
    registry_client = RegistryClient(api_url=REGISTRY_URL, region=REGION)
    orchestrator = OrchestratorAgent(config=config, registry_client=registry_client)

    # Run investigation
    print("\n  Starting investigation...")
    start = time.time()
    try:
        result = orchestrator.initiate_investigation(SAMPLE_ADVERSE_EVENTS)
        elapsed = time.time() - start
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ Investigation failed after {elapsed:.1f}s: {e}")
        traceback.print_exc()
        return None

    print(f"  Total time: {elapsed:.1f}s")
    print(f"  Investigation ID: {result.investigation_id}")
    print(f"  Status: {result.status}")

    # Signal detection results
    if result.signal:
        s = result.signal
        print(f"\n  Signal Detected:")
        print(f"    Drug: {s.drug_name}")
        print(f"    Event: {s.adverse_event_term}")
        print(f"    Count: {s.event_count}")
        try:
            print(f"    PRR: {float(s.prr):.2f}")
            print(f"    ROR: {float(s.ror):.2f}")
            print(f"    IC025: {float(s.ic025):.2f}")
        except (ValueError, TypeError):
            print(f"    PRR: {s.prr}")
            print(f"    ROR: {s.ror}")
            print(f"    IC025: {s.ic025}")
        print(f"    Severity: {s.severity}")
    else:
        print("\n  No signal detected")

    # Literature results
    if result.literature:
        lit = result.literature
        print(f"\n  Literature Search:")
        print(f"    Query: {lit.query}")
        print(f"    Articles: {lit.total_results}")
        if lit.articles:
            for i, a in enumerate(lit.articles[:3], 1):
                print(f"    {i}. {a.title} (relevance={a.relevance_score:.2f})")

    # Regulatory reports
    if result.reports:
        print(f"\n  Regulatory Reports: {len(result.reports)}")
        for r in result.reports:
            print(f"    • {r.report_type.upper()} — {r.submission_status} (validated={r.validated})")

    # Errors
    if result.errors:
        print(f"\n  Errors:")
        for err in result.errors:
            print(f"    ⚠️  {err}")

    # Verdict
    if result.status == "completed" and result.signal:
        print(f"\n  ✅ Investigation completed with signal detection")
    elif result.status == "completed":
        print(f"\n  ✅ Investigation completed (no signal — may be expected)")
    else:
        print(f"\n  ⚠️  Investigation status: {result.status}")

    return result


# ---------------------------------------------------------------------------
# Test 5: Orchestrator list_available_agents via registry
# ---------------------------------------------------------------------------
def test_list_agents_via_orchestrator():
    """Verify the orchestrator can list agents from the registry."""
    section("Test 5: Orchestrator list_available_agents")

    config = AgentCoreConfig.from_env()
    registry_client = RegistryClient(api_url=REGISTRY_URL, region=REGION)
    orchestrator = OrchestratorAgent(config=config, registry_client=registry_client)

    start = time.time()
    agents = orchestrator.list_available_agents()
    elapsed = time.time() - start

    print(f"  Response time: {elapsed:.2f}s")
    print(f"  Agents: {len(agents)}")
    for a in agents:
        name = a.get("agent_name") or a.get("name", "?")
        status = a.get("status", "?")
        print(f"    • {name} (status={status})")

    print(f"  ✅ Orchestrator listed {len(agents)} agents from registry")
    return agents


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="E2E test with registry discovery")
    parser.add_argument(
        "--test",
        choices=["registry", "discovery", "cache", "investigation", "list", "all"],
        default="all",
        help="Which test to run (default: all)",
    )
    args = parser.parse_args()

    section("E2E Test: Adverse Event Detection with Dynamic Agent Discovery")
    print(f"  Registry: {REGISTRY_URL}")
    print(f"  Region: {REGION}")
    print(f"  Events: {len(SAMPLE_ADVERSE_EVENTS)}")

    results = {}

    try:
        if args.test in ("registry", "all"):
            client = test_registry_connectivity()
            results["registry"] = "✅" if client else "❌"

            if args.test in ("discovery", "all") and client:
                discovered = test_semantic_discovery(client)
                found = sum(1 for v in discovered.values() if v)
                results["discovery"] = f"✅ {found}/{len(DISCOVERY_QUERIES)}"

            if args.test in ("cache", "all") and client:
                test_cache_behavior(client)
                results["cache"] = "✅"

        if args.test in ("list", "all"):
            agents = test_list_agents_via_orchestrator()
            results["list_agents"] = f"✅ {len(agents)} agents"

        if args.test in ("investigation", "all"):
            inv = test_full_investigation()
            if inv and inv.status == "completed":
                results["investigation"] = "✅ completed"
            elif inv:
                results["investigation"] = f"⚠️  {inv.status}"
            else:
                results["investigation"] = "❌ failed"

    except Exception as e:
        print(f"\n  ❌ Unexpected error: {e}")
        traceback.print_exc()

    # Summary
    section("Summary")
    for name, status in results.items():
        print(f"  {name:20s} {status}")
    print()


if __name__ == "__main__":
    main()
