"""
Signal Detection Tool for adverse event analysis.

Analyzes adverse event reports using disproportionality analysis (PRR, ROR, IC025)
to detect potential safety signals.
"""

import json
import logging
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

from strands import tool

logger = logging.getLogger("detect_signals")
logger.setLevel(logging.INFO)


def _build_contingency_table(
    drug: str, event: str, events: List[Dict]
) -> Tuple[int, int, int, int]:
    """Build 2x2 contingency table for a drug-event combination."""
    a = sum(1 for e in events if e["drug_name"] == drug and e["adverse_event_term"] == event)
    b = sum(1 for e in events if e["drug_name"] == drug and e["adverse_event_term"] != event)
    c = sum(1 for e in events if e["drug_name"] != drug and e["adverse_event_term"] == event)
    d = sum(1 for e in events if e["drug_name"] != drug and e["adverse_event_term"] != event)
    return a, b, c, d


def _calculate_metrics(a: int, b: int, c: int, d: int) -> Dict[str, Any]:
    """Calculate PRR, ROR, IC025 from contingency table values."""
    # PRR & ROR
    if b == 0 or c == 0:
        prr = float("inf") if a > 0 else 0.0
        ror = float("inf") if a > 0 else 0.0
    else:
        prr = (a * d) / (b * c)
        ror = (a * d) / (b * c)

    # Expected count
    total = a + b + c + d
    expected = ((a + b) * (a + c)) / total if total > 0 else 0.0

    # IC025 (lower bound of 95% CI for Information Component)
    if expected > 0 and a > 0:
        ic = math.log2(a / expected)
        se = math.sqrt(1 / a)
        ic025 = ic - 1.96 * se
        ic975 = ic + 1.96 * se
    else:
        ic025 = -float("inf")
        ic975 = float("inf")

    return {
        "prr": prr,
        "ror": ror,
        "ic025": ic025,
        "confidence_interval": [ic025, ic975],
        "event_count": a,
        "expected_count": expected,
    }


def _determine_severity(ic025: float, event_count: int) -> str:
    """Determine signal severity based on IC025 and event count."""
    if ic025 > 3.0 and event_count >= 10:
        return "critical"
    elif ic025 > 2.0 and event_count >= 5:
        return "high"
    elif ic025 > 1.0:
        return "medium"
    return "low"


def detect_signals(adverse_events_json: str) -> dict:
    """
    Analyze adverse event reports to detect potential safety signals.

    Uses disproportionality analysis (PRR, ROR, IC025) on a set of adverse event
    reports to identify drug-event combinations that occur more frequently than
    expected, which may indicate a safety signal.

    Args:
        adverse_events_json: JSON string containing a list of adverse event objects.
            Each object must have at minimum: event_id, drug_name, adverse_event_term,
            medra_code, event_date, outcome, reporter_type.
            Optional fields: patient_age, patient_sex.

    Returns:
        Dictionary with status and content containing detected signals with
        statistical metrics, severity classification, and analysis summary.

    Example input:
        '[{"event_id":"E1","drug_name":"DrugA","adverse_event_term":"Headache",
          "medra_code":"10019211","event_date":"2025-01-15","outcome":"recovered",
          "reporter_type":"physician"}]'
    """
    try:
        events = json.loads(adverse_events_json)
        if not events:
            return {"status": "error", "content": [{"text": "No adverse events provided"}]}

        # Validate required fields
        required = ["event_id", "drug_name", "adverse_event_term"]
        for i, e in enumerate(events):
            for field in required:
                if not e.get(field):
                    return {
                        "status": "error",
                        "content": [{"text": f"Event {i}: missing required field '{field}'"}],
                    }

        # Group by drug-event combination
        combos: Dict[Tuple[str, str], List[Dict]] = {}
        for e in events:
            key = (e["drug_name"], e["adverse_event_term"])
            combos.setdefault(key, []).append(e)

        signals = []
        errors = []

        for (drug, event_term), specific in combos.items():
            try:
                a, b, c, d = _build_contingency_table(drug, event_term, events)
                if a == 0:
                    continue
                metrics = _calculate_metrics(a, b, c, d)
                severity = _determine_severity(metrics["ic025"], metrics["event_count"])

                signal = {
                    "signal_id": f"SIG_{drug}_{event_term}_{int(time.time())}",
                    "drug_name": drug,
                    "adverse_event_term": event_term,
                    "severity": severity,
                    "flagged": metrics["ic025"] > 0,
                    **metrics,
                }
                signals.append(signal)
            except Exception as ex:
                errors.append(f"Error analyzing {drug}-{event_term}: {str(ex)}")

        # Format output
        lines = [f"Analyzed {len(events)} adverse event reports across {len(combos)} drug-event combinations.\n"]

        flagged = [s for s in signals if s["flagged"]]
        lines.append(f"Detected {len(flagged)} flagged signal(s) (IC025 > 0):\n")

        for s in sorted(signals, key=lambda x: x["ic025"], reverse=True):
            flag = "⚠️" if s["flagged"] else "  "
            lines.append(
                f"{flag} {s['drug_name']} + {s['adverse_event_term']} "
                f"[{s['severity'].upper()}]\n"
                f"   PRR={s['prr']:.2f}  ROR={s['ror']:.2f}  IC025={s['ic025']:.2f}  "
                f"Events={s['event_count']}  Expected={s['expected_count']:.2f}\n"
            )

        if errors:
            lines.append(f"\nErrors: {'; '.join(errors)}")

        # Also include structured JSON for downstream tools
        lines.append(f"\n---SIGNALS_JSON---\n{json.dumps(signals, default=str)}")

        return {"status": "success", "content": [{"text": "\n".join(lines)}]}

    except json.JSONDecodeError as e:
        return {"status": "error", "content": [{"text": f"Invalid JSON input: {str(e)}"}]}
    except Exception as e:
        logger.error(f"Signal detection error: {e}", exc_info=True)
        return {"status": "error", "content": [{"text": f"Signal detection failed: {str(e)}"}]}


@tool
def detect_signals_tool(adverse_events_json: str) -> dict:
    """Analyze adverse event reports to detect potential safety signals using disproportionality analysis (PRR, ROR, IC025).

    Args:
        adverse_events_json: JSON string containing a list of adverse event objects. Each object must have: event_id, drug_name, adverse_event_term, medra_code, event_date, outcome, reporter_type. Optional: patient_age, patient_sex.

    Returns:
        dict: ToolResult with status and content containing detected signals with statistical metrics and severity.
    """
    return detect_signals(adverse_events_json)
