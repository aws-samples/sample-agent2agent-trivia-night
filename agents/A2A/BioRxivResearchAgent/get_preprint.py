import logging
from typing import Optional

import httpx
from strands import tool

logger = logging.getLogger("get_preprint")
logger.setLevel(logging.INFO)

BASE_URL = "https://api.biorxiv.org"


def get_preprint(doi: str, server: str = "biorxiv") -> dict:
    """
    Retrieve full details for a specific preprint by DOI.

    Fetches all versions of a preprint and returns the most recent version
    with complete metadata including abstract.

    Args:
        doi: The DOI of the preprint (e.g. "10.1101/2024.01.01.123456").
        server: "biorxiv" or "medrxiv".

    Returns:
        ToolResult dict with status and content.
    """
    try:
        url = f"{BASE_URL}/details/{server}/{doi}/na/json"
        logger.info(f"Fetching preprint details for DOI: {doi}")

        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        collection = data.get("collection", [])
        if not collection:
            return {
                "status": "error",
                "content": [{"text": f"No preprint found for DOI: {doi} on {server}"}],
            }

        # Return the latest version (last in the list)
        article = collection[-1]

        lines = [
            f"Title: {article.get('title', 'No title')}",
            f"Authors: {article.get('authors', 'No authors')}",
            f"Corresponding Author: {article.get('author_corresponding', 'N/A')} ({article.get('author_corresponding_institution', 'N/A')})",
            f"Category: {article.get('category', 'N/A')}",
            f"Date: {article.get('date', 'N/A')}",
            f"DOI: {article.get('doi', 'N/A')}",
            f"Version: {article.get('version', 'N/A')} (of {len(collection)} total)",
            f"License: {article.get('license', 'N/A')}",
            f"Published: {article.get('published', 'Not yet')}",
            f"URL: https://doi.org/{article.get('doi', '')}",
            "",
            f"Abstract: {article.get('abstract', 'No abstract available')}",
        ]

        return {
            "status": "success",
            "content": [
                {"text": "\n".join(lines)},
                {
                    "json": {
                        "doi": article.get("doi"),
                        "title": article.get("title"),
                        "date": article.get("date"),
                        "version": article.get("version"),
                        "published": article.get("published"),
                        "source": f"https://doi.org/{article.get('doi', '')}",
                    }
                },
            ],
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e}")
        return {"status": "error", "content": [{"text": f"biorxiv API HTTP error: {e.response.status_code}"}]}
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        return {"status": "error", "content": [{"text": f"biorxiv API request error: {e}"}]}
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"status": "error", "content": [{"text": f"Unexpected error: {e}"}]}


@tool
def get_preprint_tool(doi: str, server: str = "biorxiv") -> dict:
    """Retrieve full details for a specific biorxiv or medrxiv preprint by DOI.

    Fetches the latest version of a preprint including title, authors,
    corresponding author, abstract, category, license, and publication status.

    Args:
        doi: The DOI of the preprint. Example: "10.1101/2024.01.01.123456"
        server: Which preprint server to query. Options:
            - "biorxiv" (default): Biology preprints
            - "medrxiv": Medical preprints

    Returns:
        Dictionary with status and content containing the full preprint details
        including abstract, author information, and publication status.

    Examples:
        Get a biorxiv preprint:
            get_preprint_tool("10.1101/2024.01.15.575789")

        Get a medrxiv preprint:
            get_preprint_tool("10.1101/2024.03.01.24303456", server="medrxiv")
    """
    return get_preprint(doi=doi, server=server)
