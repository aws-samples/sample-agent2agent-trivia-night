"""
Regulatory Report Generation Tool.

Generates FDA MedWatch and EMA EudraVigilance format reports for detected
safety signals, including statistical evidence and literature references.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from strands import tool

logger = logging.getLogger("generate_report")
logger.setLevel(logging.INFO)


def _generate_clinical_assessment(signal: Dict, literature: Optional[List[Dict]] = None) -> str:
    """Generate clinical assessment text for a regulatory report."""
    parts = [
        f"A potential safety signal has been detected for {signal['drug_name']} "
        f"associated with {signal['adverse_event_term']}.",
        f"\n\nStatistical Analysis:\n"
        f"- Event Count: {signal.get('event_count', 'N/A')} reports\n"
        f"- Expected Count: {signal.get('expected_count', 0):.2f} reports\n"
        f"- Proportional Reporting Ratio (PRR): {signal.get('prr', 0):.2f}\n"
        f"- Reporting Odds Ratio (ROR): {signal.get('ror', 0):.2f}\n"
        f"- Information Component (IC025): {signal.get('ic025', 0):.2f}\n"
        f"- 95% Confidence Interval: ({signal.get('confidence_interval', [0, 0])[0]:.2f}, "
        f"{signal.get('confidence_interval', [0, 0])[1]:.2f})",
    ]

    severity = signal.get("severity", "low")
    severity_text = {
        "critical": "This signal is classified as CRITICAL and requires immediate investigation.",
        "high": "This signal is classified as HIGH priority and warrants prompt investigation.",
        "medium": "This signal is classified as MEDIUM priority and should be monitored closely.",
        "low": "This signal is classified as LOW priority but should be tracked.",
    }
    parts.append(f"\n\n{severity_text.get(severity, '')}")

    if literature:
        parts.append(f"\n\nLiterature Review:\n{len(literature)} relevant publication(s) found.")
        for i, article in enumerate(literature[:3], 1):
            pmid = article.get("pmid", "N/A")
            parts.append(f"  {i}. {article.get('title', 'Untitled')} (PMID: {pmid})")
    else:
        parts.append(
            "\n\nLiterature Review:\n"
            "No published literature was found for this drug-event combination. "
            "This may represent a novel safety signal requiring further investigation."
        )

    parts.append(
        "\n\nRecommendations:\n"
        "1. Conduct detailed case review of all reported events\n"
        "2. Assess temporal relationship between drug exposure and event onset\n"
        "3. Evaluate alternative explanations and confounding factors\n"
        "4. Consider additional pharmacoepidemiological studies if signal persists\n"
        "5. Update product labeling if causal relationship is established"
    )

    return "".join(parts)


def _validate_report(report: Dict) -> Dict:
    """Validate a regulatory report against schema requirements."""
    errors = []
    warnings = []

    if not report.get("signal", {}).get("drug_name"):
        errors.append("Signal must have drug_name")
    if not report.get("signal", {}).get("adverse_event_term"):
        errors.append("Signal must have adverse_event_term")
    if report.get("signal", {}).get("event_count", 0) <= 0:
        errors.append("Signal must have positive event_count")
    if not report.get("clinical_assessment"):
        errors.append("Clinical assessment is required")
    elif len(report.get("clinical_assessment", "")) < 50:
        warnings.append("Clinical assessment is very brief")

    signal = report.get("signal", {})
    if signal.get("prr") is None:
        warnings.append("PRR metric is missing")
    if signal.get("ror") is None:
        warnings.append("ROR metric is missing")
    if signal.get("ic025") is None:
        warnings.append("IC025 metric is missing")

    return {"is_valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def _build_report(
    report_type: str, signal: Dict, literature: Optional[List[Dict]]
) -> Dict:
    """Build a single regulatory report."""
    prefix = "MW" if report_type == "medwatch" else "EV"
    ts = int(datetime.now().timestamp())
    report_id = f"{prefix}_{signal.get('signal_id', 'unknown')}_{ts}"

    clinical_assessment = _generate_clinical_assessment(signal, literature)

    report = {
        "report_id": report_id,
        "report_type": report_type,
        "generated_at": datetime.now().isoformat(),
        "submission_status": "draft",
        "signal": signal,
        "clinical_assessment": clinical_assessment,
        "literature_references": literature or [],
        "validated": False,
    }

    validation = _validate_report(report)
    report["validated"] = validation["is_valid"]
    report["validation"] = validation

    return report


def generate_report(signal_json: str, literature_json: str = "[]") -> dict:
    """
    Generate FDA MedWatch and EMA EudraVigilance regulatory reports for a safety signal.

    Creates structured regulatory reports including signal description, statistical
    evidence, literature references, clinical assessment, and recommendations.
    Both MedWatch (FDA) and EudraVigilance (EMA) format reports are generated.

    Args:
        signal_json: JSON string containing the detected signal object with fields:
            signal_id, drug_name, adverse_event_term, event_count, expected_count,
            prr, ror, ic025, confidence_interval, severity.
        literature_json: Optional JSON string containing a list of literature article
            objects with fields: title, authors, journal, pmid, doi, abstract.
            Defaults to empty list.

    Returns:
        Dictionary with status and content containing both MedWatch and
        EudraVigilance reports with validation results.

    Example:
        generate_report(
            '{"signal_id":"SIG_1","drug_name":"DrugA","adverse_event_term":"Headache",...}',
            '[{"title":"Study on DrugA","authors":["Smith"],...}]'
        )
    """
    try:
        signal = json.loads(signal_json)
        literature = json.loads(literature_json) if literature_json else []

        if not signal:
            return {"status": "error", "content": [{"text": "No signal data provided"}]}
        if not signal.get("drug_name") or not signal.get("adverse_event_term"):
            return {
                "status": "error",
                "content": [{"text": "Signal must have drug_name and adverse_event_term"}],
            }

        # Generate both report types
        medwatch = _build_report("medwatch", signal, literature)
        eudravigilance = _build_report("eudravigilance", signal, literature)

        # Format output
        lines = [
            f"Generated regulatory reports for {signal['drug_name']} + {signal['adverse_event_term']}\n",
            "=" * 60,
            f"MedWatch (FDA) Report: {medwatch['report_id']}",
            f"  Validated: {medwatch['validated']}",
        ]
        if medwatch["validation"]["warnings"]:
            lines.append(f"  Warnings: {', '.join(medwatch['validation']['warnings'])}")
        if medwatch["validation"]["errors"]:
            lines.append(f"  Errors: {', '.join(medwatch['validation']['errors'])}")

        lines.extend([
            "",
            f"EudraVigilance (EMA) Report: {eudravigilance['report_id']}",
            f"  Validated: {eudravigilance['validated']}",
        ])
        if eudravigilance["validation"]["warnings"]:
            lines.append(f"  Warnings: {', '.join(eudravigilance['validation']['warnings'])}")

        lines.extend([
            "",
            "=" * 60,
            "Clinical Assessment:",
            medwatch["clinical_assessment"],
        ])

        reports = [medwatch, eudravigilance]
        lines.append(f"\n---REPORTS_JSON---\n{json.dumps(reports, default=str)}")

        return {"status": "success", "content": [{"text": "\n".join(lines)}]}

    except json.JSONDecodeError as e:
        return {"status": "error", "content": [{"text": f"Invalid JSON input: {str(e)}"}]}
    except Exception as e:
        logger.error(f"Report generation error: {e}", exc_info=True)
        return {"status": "error", "content": [{"text": f"Report generation failed: {str(e)}"}]}


@tool
def generate_report_tool(signal_json: str, literature_json: str = "[]") -> dict:
    """Generate FDA MedWatch and EMA EudraVigilance regulatory reports for a detected safety signal.

    Args:
        signal_json: JSON string containing the detected signal with fields: signal_id, drug_name, adverse_event_term, event_count, expected_count, prr, ror, ic025, confidence_interval, severity.
        literature_json: Optional JSON string containing literature articles. Defaults to empty list.

    Returns:
        dict: ToolResult with status and content containing both regulatory reports.
    """
    return generate_report(signal_json, literature_json)
