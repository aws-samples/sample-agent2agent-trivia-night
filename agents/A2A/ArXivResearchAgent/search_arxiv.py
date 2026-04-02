import logging
from typing import Any, Dict, List, Optional
import httpx
from defusedxml import ElementTree as ET
from defusedxml.ElementTree import Element
from strands import tool

logger = logging.getLogger("search_arxiv")
logger.setLevel(logging.INFO)

SEARCH_URL = "http://export.arxiv.org/api/query"

# Atom / OpenSearch namespaces
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}

ArticleDict = Dict[str, Any]


def _parse_entry(entry: Element) -> ArticleDict:
    """Parse a single Atom <entry> into an article dict."""

    def _text(tag: str) -> str:
        el = entry.find(tag, NS)
        return (el.text or "").strip() if el is not None else ""

    article: ArticleDict = {}

    article["title"] = " ".join(_text("atom:title").split())
    article["abstract"] = " ".join(_text("atom:summary").split())
    article["published"] = _text("atom:published")
    article["updated"] = _text("atom:updated")

    # arXiv ID from the <id> URL
    raw_id = _text("atom:id")
    if raw_id:
        article["arxiv_id"] = raw_id.replace("http://arxiv.org/abs/", "")
        article["url"] = raw_id

    # Authors
    authors = []
    for author_el in entry.findall("atom:author", NS):
        name_el = author_el.find("atom:name", NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())
    article["authors"] = ", ".join(authors) if authors else "No authors listed"

    # Categories
    categories = []
    for cat_el in entry.findall("atom:category", NS):
        term = cat_el.get("term", "")
        if term:
            categories.append(term)
    article["categories"] = ", ".join(categories) if categories else "N/A"

    # Primary category
    primary = entry.find("arxiv:primary_category", NS)
    if primary is not None:
        article["primary_category"] = primary.get("term", "N/A")

    # Links (PDF, DOI)
    for link_el in entry.findall("atom:link", NS):
        rel = link_el.get("rel", "")
        href = link_el.get("href", "")
        link_type = link_el.get("type", "")
        if link_type == "application/pdf":
            article["pdf_url"] = href
        elif rel == "related" and "doi" in href:
            article["doi"] = href

    # Journal ref and comment
    journal_ref = entry.find("arxiv:journal_ref", NS)
    if journal_ref is not None and journal_ref.text:
        article["journal_ref"] = journal_ref.text.strip()

    comment = entry.find("arxiv:comment", NS)
    if comment is not None and comment.text:
        article["comment"] = comment.text.strip()

    return article


def search_arxiv(
    query: str,
    max_results: int = 20,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    category: Optional[str] = None,
) -> dict:
    """
    Search arXiv for papers matching a query.

    Args:
        query: Search query (supports arXiv syntax: ti:, au:, abs:, cat:, all:).
        max_results: Maximum results to return (default 20, max 200).
        sort_by: "relevance", "lastUpdatedDate", or "submittedDate".
        sort_order: "ascending" or "descending".
        category: Optional category filter (e.g. "q-bio.GN", "cs.AI", "stat.ML").

    Returns:
        ToolResult dict with status and content.
    """
    try:
        max_results = min(max_results, 200)

        search_query = f"all:{query}"
        if category:
            search_query = f"cat:{category} AND {search_query}"

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        logger.info(f"Searching arXiv: {search_query}")

        response = httpx.get(SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.text)

        total_el = root.find("opensearch:totalResults", NS)
        total = int(total_el.text) if total_el is not None and total_el.text else 0

        entries = root.findall("atom:entry", NS)
        if not entries:
            return {
                "status": "success",
                "content": [{"text": f"No papers found on arXiv for '{query}'."}],
            }

        articles = []
        for entry in entries:
            article = _parse_entry(entry)
            if article.get("title"):
                articles.append(article)

        formatted = _format_results(articles, total)
        return {"status": "success", "content": [{"text": formatted}]}

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e}")
        return {"status": "error", "content": [{"text": f"arXiv API HTTP error: {e.response.status_code}"}]}
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        return {"status": "error", "content": [{"text": f"arXiv API request error: {e}"}]}
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"status": "error", "content": [{"text": f"Unexpected error: {e}"}]}


def _format_results(articles: List[ArticleDict], total: int) -> str:
    """Format a list of arXiv articles into readable text."""
    lines = [f"Showing {len(articles)} of {total} papers found", ""]

    for i, article in enumerate(articles, 1):
        lines.append(f"Paper {i}")
        lines.append("-" * 20)
        lines.append(f"Title: {article.get('title', 'No title')}")
        lines.append(f"Authors: {article.get('authors', 'No authors')}")
        lines.append(f"Categories: {article.get('categories', 'N/A')}")
        lines.append(f"Published: {article.get('published', 'N/A')}")
        lines.append(f"arXiv ID: {article.get('arxiv_id', 'N/A')}")

        if article.get("journal_ref"):
            lines.append(f"Journal: {article['journal_ref']}")

        pdf_url = article.get("pdf_url", "")
        if pdf_url:
            lines.append(f"PDF: {pdf_url}")

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
def search_arxiv_tool(
    query: str,
    max_results: int = 20,
    sort_by: str = "relevance",
    category: Optional[str] = None,
) -> dict:
    """Search arXiv for scientific papers matching a query.

    This tool performs full-text search across arXiv papers including titles,
    abstracts, and metadata. Ideal for finding computational, mathematical,
    and quantitative research including ML/AI for biology, bioinformatics,
    statistical methods, and biophysics.

    Args:
        query: Search terms. Supports arXiv query syntax:
            - Simple keywords: "protein structure prediction"
            - Title search: "ti:transformer"
            - Author search: "au:hinton"
            - Abstract search: "abs:drug discovery"
            - Boolean operators: "CRISPR AND deep learning"
        max_results: Maximum number of results to return (default: 20, max: 200).
        sort_by: How to sort results. Options:
            - "relevance" (default): Most relevant first
            - "submittedDate": Most recently submitted first
            - "lastUpdatedDate": Most recently updated first
        category: Optional arXiv category filter. Relevant categories:
            - q-bio.BM (Biomolecules), q-bio.GN (Genomics)
            - q-bio.MN (Molecular Networks), q-bio.NC (Neurons and Cognition)
            - q-bio.QM (Quantitative Methods), q-bio.PE (Populations and Evolution)
            - cs.AI (Artificial Intelligence), cs.LG (Machine Learning)
            - cs.CE (Computational Engineering), stat.ML (Machine Learning)
            - stat.AP (Applications), physics.bio-ph (Biological Physics)

    Returns:
        Dictionary with status and content containing formatted paper results
        including titles, authors, abstracts, arXiv IDs, and PDF links.

    Examples:
        Basic search:
            search_arxiv_tool("protein structure prediction")

        Search for recent ML papers in biology:
            search_arxiv_tool("deep learning drug discovery", sort_by="submittedDate")

        Search within a specific category:
            search_arxiv_tool("single cell", category="q-bio.GN")

        Author search:
            search_arxiv_tool("au:alphafold", sort_by="submittedDate")
    """
    return search_arxiv(
        query=query,
        max_results=max_results,
        sort_by=sort_by,
        category=category,
    )
