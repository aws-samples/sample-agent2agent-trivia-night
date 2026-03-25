import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx
from strands import tool

logger = logging.getLogger("search_biorxiv")
logger.setLevel(logging.INFO)

BASE_URL = "https://api.biorxiv.org"

ArticleDict = Dict[str, Any]


def _fetch_page(endpoint: str, cursor: int = 0) -> dict:
    """Fetch a single page (up to 100 results) from the biorxiv API."""
    url = f"{BASE_URL}/{endpoint}/{cursor}/json"
    response = httpx.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def search_biorxiv(
    query: str,
    server: str = "biorxiv",
    days_back: int = 30,
    max_results: int = 20,
    category: Optional[str] = None,
) -> dict:
    """
    Search biorxiv/medrxiv for preprints published within a date range.

    The biorxiv API does not support full-text search. This function fetches
    recent preprints by date range and filters locally by matching the query
    terms against title and abstract.

    Args:
        query: Search terms to match against title and abstract.
        server: "biorxiv" or "medrxiv".
        days_back: How many days back to search (default 30, max 180).
        max_results: Maximum number of matching results to return.
        category: Optional category filter (e.g. "genomics", "bioinformatics").

    Returns:
        ToolResult dict with status and content.
    """
    try:
        days_back = min(days_back, 180)
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        interval = f"{start_date.isoformat()}/{end_date.isoformat()}"

        logger.info(f"Searching {server} for '{query}' in interval {interval}")

        # Fetch pages until we have enough matches or exhaust results
        all_articles: List[ArticleDict] = []
        cursor = 0
        total = None

        while True:
            endpoint = f"details/{server}/{interval}"
            if category:
                endpoint += f"?category={category}"

            data = _fetch_page(endpoint, cursor)
            messages = data.get("messages", [{}])
            collection = data.get("collection", [])

            if not collection:
                break

            if total is None and messages:
                total = int(messages[0].get("total", 0))
                logger.info(f"Total preprints in range: {total}")

            all_articles.extend(collection)
            cursor += 100

            # Stop if we've fetched everything or have enough raw results
            if cursor >= (total or 0) or len(all_articles) >= max_results * 10:
                break

        if not all_articles:
            return {
                "status": "success",
                "content": [{"text": f"No preprints found on {server} for the given date range."}],
            }

        # Local keyword filtering
        query_terms = query.lower().split()
        matched = []
        for article in all_articles:
            text = f"{article.get('title', '')} {article.get('abstract', '')}".lower()
            if all(term in text for term in query_terms):
                matched.append(article)

        if not matched:
            return {
                "status": "success",
                "content": [{"text": f"Found {len(all_articles)} preprints in date range but none matched '{query}'."}],
            }

        # Trim to max_results
        matched = matched[:max_results]

        formatted = _format_results(matched, len(all_articles))
        return {"status": "success", "content": [{"text": formatted}]}

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e}")
        return {"status": "error", "content": [{"text": f"biorxiv API HTTP error: {e.response.status_code}"}]}
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        return {"status": "error", "content": [{"text": f"biorxiv API request error: {e}"}]}
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"status": "error", "content": [{"text": f"Unexpected error: {e}"}]}


def _format_results(articles: List[ArticleDict], total_in_range: int) -> str:
    """Format a list of biorxiv articles into readable text."""
    lines = [f"Showing {len(articles)} matching preprints (from {total_in_range} in date range)", ""]

    for i, article in enumerate(articles, 1):
        lines.append(f"Article {i}")
        lines.append("-" * 20)
        lines.append(f"Title: {article.get('title', 'No title')}")
        lines.append(f"Authors: {article.get('authors', 'No authors')}")
        lines.append(f"Category: {article.get('category', 'N/A')}")
        lines.append(f"Date: {article.get('date', 'N/A')}")
        lines.append(f"DOI: {article.get('doi', 'N/A')}")
        lines.append(f"Version: {article.get('version', 'N/A')}")
        lines.append(f"License: {article.get('license', 'N/A')}")

        abstract = article.get("abstract", "No abstract available")
        if len(abstract) > 500:
            abstract = abstract[:497] + "..."
        lines.append(f"Abstract: {abstract}")

        if i < len(articles):
            lines.append("")
            lines.append("=" * 50)
            lines.append("")

    return "\n".join(lines)


@tool
def search_biorxiv_tool(
    query: str,
    server: str = "biorxiv",
    days_back: int = 30,
    max_results: int = 20,
    category: Optional[str] = None,
) -> dict:
    """Search biorxiv or medrxiv for recent preprints matching a query.

    This tool searches recent preprints by fetching articles from a date range
    and filtering by keyword matches against title and abstract. Ideal for
    finding the latest research on a topic before peer-reviewed publication.

    Args:
        query: Search terms to match against title and abstract. All terms must
            appear (AND logic). Example: "CRISPR gene therapy"
        server: Which preprint server to search. Options:
            - "biorxiv" (default): Biology preprints
            - "medrxiv": Medical preprints
        days_back: Number of days back to search (default: 30, max: 180).
            Larger values fetch more data but take longer.
        max_results: Maximum number of matching results to return (default: 20).
        category: Optional category filter. Examples for biorxiv:
            "genomics", "bioinformatics", "cell_biology", "neuroscience",
            "immunology", "cancer_biology", "genetics", "molecular_biology"

    Returns:
        Dictionary with status and content containing formatted preprint results
        including titles, authors, abstracts, DOIs, and publication dates.

    Examples:
        Basic search:
            search_biorxiv_tool("CRISPR gene editing")

        Search medrxiv for recent clinical trials:
            search_biorxiv_tool("clinical trial GLP-1", server="medrxiv", days_back=60)

        Search with category filter:
            search_biorxiv_tool("single cell RNA", category="genomics", days_back=14)
    """
    return search_biorxiv(
        query=query,
        server=server,
        days_back=days_back,
        max_results=max_results,
        category=category,
    )
