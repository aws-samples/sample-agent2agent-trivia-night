import logging
import httpx
from defusedxml import ElementTree as ET
from defusedxml.ElementTree import Element
from strands import tool

logger = logging.getLogger("get_paper")
logger.setLevel(logging.INFO)

SEARCH_URL = "http://export.arxiv.org/api/query"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def get_paper(arxiv_id: str) -> dict:
    """
    Retrieve full details for a specific arXiv paper by ID.

    Args:
        arxiv_id: The arXiv identifier (e.g. "2401.12345" or "2401.12345v2").

    Returns:
        ToolResult dict with status and content.
    """
    try:
        # Strip any URL prefix if the user passed a full URL
        arxiv_id = arxiv_id.replace("http://arxiv.org/abs/", "").replace("https://arxiv.org/abs/", "")

        logger.info(f"Fetching arXiv paper: {arxiv_id}")

        response = httpx.get(SEARCH_URL, params={"id_list": arxiv_id}, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        entries = root.findall("atom:entry", NS)

        if not entries:
            return {
                "status": "error",
                "content": [{"text": f"No paper found for arXiv ID: {arxiv_id}"}],
            }

        entry = entries[0]

        def _text(tag: str) -> str:
            el = entry.find(tag, NS)
            return (el.text or "").strip() if el is not None else ""

        title = " ".join(_text("atom:title").split())

        # Check for error entries (arXiv returns an entry with "Error" as id)
        entry_id = _text("atom:id")
        if not title or "error" in entry_id.lower():
            return {
                "status": "error",
                "content": [{"text": f"No paper found for arXiv ID: {arxiv_id}"}],
            }

        abstract = " ".join(_text("atom:summary").split())

        # Authors with affiliations
        authors = []
        for author_el in entry.findall("atom:author", NS):
            name_el = author_el.find("atom:name", NS)
            if name_el is not None and name_el.text:
                name = name_el.text.strip()
                affiliations = []
                for aff_el in author_el.findall("arxiv:affiliation", NS):
                    if aff_el.text:
                        affiliations.append(aff_el.text.strip())
                if affiliations:
                    name += f" ({', '.join(affiliations)})"
                authors.append(name)

        # Categories
        categories = []
        for cat_el in entry.findall("atom:category", NS):
            term = cat_el.get("term", "")
            if term:
                categories.append(term)

        # Links
        pdf_url = ""
        for link_el in entry.findall("atom:link", NS):
            if link_el.get("type", "") == "application/pdf":
                pdf_url = link_el.get("href", "")

        lines = [
            f"Title: {title}",
            f"Authors: {', '.join(authors) if authors else 'No authors listed'}",
            f"Categories: {', '.join(categories) if categories else 'N/A'}",
            f"Published: {_text('atom:published')}",
            f"Updated: {_text('atom:updated')}",
            f"arXiv ID: {arxiv_id}",
            f"URL: https://arxiv.org/abs/{arxiv_id}",
        ]

        if pdf_url:
            lines.append(f"PDF: {pdf_url}")

        journal_ref = entry.find("arxiv:journal_ref", NS)
        if journal_ref is not None and journal_ref.text:
            lines.append(f"Journal: {journal_ref.text.strip()}")

        comment = entry.find("arxiv:comment", NS)
        if comment is not None and comment.text:
            lines.append(f"Comment: {comment.text.strip()}")

        doi_el = entry.find("arxiv:doi", NS)
        if doi_el is not None and doi_el.text:
            lines.append(f"DOI: https://doi.org/{doi_el.text.strip()}")

        lines.append("")
        lines.append(f"Abstract: {abstract}")

        return {
            "status": "success",
            "content": [
                {"text": "\n".join(lines)},
                {
                    "json": {
                        "arxiv_id": arxiv_id,
                        "title": title,
                        "published": _text("atom:published"),
                        "categories": categories,
                        "source": f"https://arxiv.org/abs/{arxiv_id}",
                    }
                },
            ],
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e}")
        return {"status": "error", "content": [{"text": f"arXiv API HTTP error: {e.response.status_code}"}]}
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        return {"status": "error", "content": [{"text": f"arXiv API request error: {e}"}]}
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"status": "error", "content": [{"text": f"Unexpected error: {e}"}]}


@tool
def get_paper_tool(arxiv_id: str) -> dict:
    """Retrieve full details for a specific arXiv paper by its ID.

    Fetches complete metadata including title, all authors with affiliations,
    full abstract, categories, publication dates, and links to PDF and DOI.

    Args:
        arxiv_id: The arXiv identifier. Accepts multiple formats:
            - Just the ID: "2401.12345"
            - With version: "2401.12345v2"
            - Full URL: "https://arxiv.org/abs/2401.12345"

    Returns:
        Dictionary with status and content containing the full paper details
        including abstract, author affiliations, and links.

    Examples:
        Get a paper by ID:
            get_paper_tool("2401.12345")

        Get a specific version:
            get_paper_tool("2401.12345v2")
    """
    return get_paper(arxiv_id=arxiv_id)
