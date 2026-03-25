"""
Literature Search Tool for adverse event signal investigation.

Searches PubMed Central for published evidence related to detected safety signals.
Uses the NCBI E-utilities API for article search and retrieval.
"""

import json
import logging
import os
from typing import Any, Dict, List, Literal

from defusedxml import ElementTree as ET

import httpx
from strands import tool

logger = logging.getLogger("search_literature")
logger.setLevel(logging.INFO)

NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _get_api_params(params: dict) -> dict:
    """Add NCBI API key to params if available."""
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    return params


def _build_safety_query(drug_name: str, adverse_event_term: str) -> str:
    """Build a PubMed search query for a drug-event safety signal."""
    return (
        f'"{drug_name}"[Title/Abstract] AND '
        f'"{adverse_event_term}"[Title/Abstract] AND '
        f"(adverse OR safety OR toxicity OR side effect OR pharmacovigilance)"
    )


def _fetch_article_details(pmc_ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch article details from PMC for a list of IDs."""
    if not pmc_ids:
        return []

    ids_str = ",".join(pmc_ids)
    fetch_url = f"{BASE_URL}/efetch.fcgi"
    params = _get_api_params({
        "db": "pmc",
        "id": ids_str,
        "retmode": "xml",
    })

    try:
        resp = httpx.post(fetch_url, data=params, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch article details: {e}")
        return []

    articles = []
    try:
        root = ET.fromstring(resp.content)
        for article_el in root.findall(".//article"):
            title_el = article_el.find(".//article-title")
            abstract_el = article_el.find(".//abstract")
            journal_el = article_el.find(".//journal-title")
            pmid_el = article_el.find(".//article-id[@pub-id-type='pmid']")
            doi_el = article_el.find(".//article-id[@pub-id-type='doi']")

            # Extract authors
            authors = []
            for contrib in article_el.findall(".//contrib[@contrib-type='author']"):
                surname = contrib.findtext("name/surname", "")
                given = contrib.findtext("name/given-names", "")
                if surname:
                    authors.append(f"{surname} {given}".strip())

            title = title_el.text if title_el is not None and title_el.text else "Untitled"
            abstract_text = ""
            if abstract_el is not None:
                abstract_text = " ".join(abstract_el.itertext()).strip()

            articles.append({
                "title": title,
                "authors": authors or ["Unknown"],
                "journal": journal_el.text if journal_el is not None else "Unknown",
                "abstract": abstract_text or "No abstract available",
                "pmid": pmid_el.text if pmid_el is not None else None,
                "doi": doi_el.text if doi_el is not None else None,
            })
    except Exception as e:
        logger.error(f"Error parsing article XML: {e}")

    return articles


def _score_relevance(article: Dict, drug_name: str, event_term: str) -> float:
    """Score article relevance to the drug-event signal."""
    text = (article.get("title", "") + " " + article.get("abstract", "")).lower()
    score = 0.0

    if drug_name.lower() in text:
        score += 0.4
    if event_term.lower() in text:
        score += 0.4

    safety_kw = ["adverse", "safety", "toxicity", "side effect", "risk", "pharmacovigilance"]
    if any(kw in text for kw in safety_kw):
        score += 0.05

    study_kw = ["clinical trial", "case report", "meta-analysis", "cohort", "systematic review"]
    if any(kw in text for kw in study_kw):
        score += 0.15

    return min(score, 1.0)


def search_literature(drug_name: str, adverse_event_term: str, max_results: int = 20) -> dict:
    """
    Search PubMed Central for literature related to a drug safety signal.

    Searches for published evidence linking a specific drug to an adverse event,
    scores results by relevance, and returns formatted findings with citations.

    Args:
        drug_name: Name of the drug to investigate (e.g., "Aspirin").
        adverse_event_term: The adverse event term (e.g., "Gastrointestinal bleeding").
        max_results: Maximum number of articles to return (default 20).

    Returns:
        Dictionary with status and content containing relevant articles,
        relevance scores, and a summary of findings.

    Example:
        search_literature("Aspirin", "Gastrointestinal bleeding")
    """
    try:
        query = _build_safety_query(drug_name, adverse_event_term)
        logger.info(f"Searching PMC: {query}")

        # Search for article IDs
        search_url = f"{BASE_URL}/esearch.fcgi"
        search_params = _get_api_params({
            "db": "pmc",
            "term": query,
            "retmax": min(max_results * 5, 200),  # fetch more, filter later
            "retmode": "json",
            "sort": "relevance",
        })

        search_resp = httpx.post(search_url, data=search_params, timeout=30)
        search_resp.raise_for_status()
        search_data = search_resp.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        total_found = int(search_data.get("esearchresult", {}).get("count", 0))

        if not id_list:
            return {
                "status": "success",
                "content": [{
                    "text": (
                        f"No published literature found for {drug_name} and "
                        f"{adverse_event_term}. This may represent a novel signal "
                        f"requiring further investigation."
                    )
                }],
            }

        # Fetch article details
        articles = _fetch_article_details(id_list)

        # Score and rank by relevance
        for article in articles:
            article["relevance_score"] = _score_relevance(article, drug_name, adverse_event_term)

        articles.sort(key=lambda a: a["relevance_score"], reverse=True)
        articles = [a for a in articles if a["relevance_score"] >= 0.3][:max_results]

        # Format output
        lines = [
            f"Literature search for {drug_name} + {adverse_event_term}",
            f"Found {total_found} total results, showing {len(articles)} most relevant:\n",
        ]

        for i, a in enumerate(articles, 1):
            authors_str = ", ".join(a["authors"][:3])
            if len(a["authors"]) > 3:
                authors_str += " et al."
            lines.append(
                f"Article {i} (relevance: {a['relevance_score']:.0%})\n"
                f"  Title: {a['title']}\n"
                f"  Authors: {authors_str}\n"
                f"  Journal: {a['journal']}\n"
                f"  PMID: {a.get('pmid', 'N/A')}  DOI: {a.get('doi', 'N/A')}\n"
            )

        # Summary
        case_reports = sum(1 for a in articles if "case report" in a["title"].lower())
        trials = sum(1 for a in articles if "trial" in a["title"].lower())
        meta = sum(1 for a in articles if "meta-analysis" in a["title"].lower())

        summary_parts = [f"\nSummary: {len(articles)} relevant publications identified."]
        if case_reports:
            summary_parts.append(f"{case_reports} case report(s).")
        if trials:
            summary_parts.append(f"{trials} clinical trial(s).")
        if meta:
            summary_parts.append(f"{meta} meta-analysis/analyses.")

        lines.append(" ".join(summary_parts))

        lines.append(f"\n---LITERATURE_JSON---\n{json.dumps(articles, default=str)}")

        return {"status": "success", "content": [{"text": "\n".join(lines)}]}

    except Exception as e:
        logger.error(f"Literature search error: {e}", exc_info=True)
        return {"status": "error", "content": [{"text": f"Literature search failed: {str(e)}"}]}


@tool
def search_literature_tool(drug_name: str, adverse_event_term: str, max_results: int = 20) -> dict:
    """Search PubMed Central for published evidence related to a drug safety signal.

    Args:
        drug_name: Name of the drug to investigate (e.g., "Aspirin").
        adverse_event_term: The adverse event term (e.g., "Gastrointestinal bleeding").
        max_results: Maximum number of articles to return (default 20).

    Returns:
        dict: ToolResult with status and content containing relevant articles and summary.
    """
    return search_literature(drug_name, adverse_event_term, max_results)
