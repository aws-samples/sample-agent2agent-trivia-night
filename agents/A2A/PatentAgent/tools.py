"""USPTO PPUBS tools as plain Strands @tool functions (no MCP)."""

import asyncio
import logging
from typing import Any, Dict

from strands import tool

from config import config
from constants import Sources, Fields
from util.errors import ApiError, is_error
from util.validation import validate_patent_number
from util.response import ResponseEnvelope, check_and_truncate
from resources import (
    get_cpc_section_info, get_cpc_subsection_info,
    get_status_code_info,
)
from uspto.ppubs_uspto_gov import PpubsClient

logger = logging.getLogger(__name__)

# Persistent event loop on a background thread so the httpx AsyncClient
# connection pool stays alive across tool calls.
import threading

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

_client = PpubsClient()


def _run(coro):
    """Run an async coroutine on the shared background loop."""
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


async def _search_patent_by_number(patent_number: str) -> Dict[str, Any]:
    query = f'patentNumber:"{patent_number}"'
    result = await _client.run_query(query=query, sources=[Sources.GRANTED_PATENTS], limit=1)
    if is_error(result):
        return result
    patents = result.get(Fields.PATENTS, result.get(Fields.DOCS, []))
    if patents:
        return {"success": True, "patent": patents[0]}
    alt = f'"{patent_number}".pn.'
    result = await _client.run_query(query=alt, sources=[Sources.GRANTED_PATENTS], limit=1)
    if is_error(result):
        return result
    patents = result.get(Fields.PATENTS, result.get(Fields.DOCS, []))
    if not patents:
        return ApiError.not_found("Patent", patent_number)
    return {"success": True, "patent": patents[0]}


@tool
def check_api_status() -> Dict[str, Any]:
    """Check status and availability of the Patent Public Search API."""
    return {"success": True, "source": "ppubs", "configured": True, "requires_auth": False}


@tool
def get_cpc_info(cpc_code: str) -> Dict[str, Any]:
    """Look up CPC classification code information.

    Args:
        cpc_code: CPC code (e.g. "G06", "G06N3/08", or section letter "A"-"H","Y")
    """
    return get_cpc_section_info(cpc_code) if len(cpc_code) == 1 else get_cpc_subsection_info(cpc_code)


@tool
def get_status_code(code: str) -> Dict[str, Any]:
    """Look up USPTO application status code meaning.

    Args:
        code: Status code number (e.g. "30")
    """
    return get_status_code_info(code)


@tool
def ppubs_search_patents(query: str, offset: int = 0, limit: int = 100, sort: str = "date_publ desc") -> Dict[str, Any]:
    """Search granted US patents via PPUBS full-text search.

    Args:
        query: USPTO search syntax (e.g. TTL/"machine learning", IN/Smith AND AN/IBM, CPC/G06N3/08)
        offset: Pagination start (default 0)
        limit: Max results (default 100, max 500)
        sort: Sort order (default "date_publ desc")
    """
    async def _search():
        result = await _client.run_query(query=query, start=offset, limit=min(limit, 500), sort=sort, sources=[Sources.GRANTED_PATENTS])
        if is_error(result):
            return result
        return check_and_truncate(ResponseEnvelope.from_ppubs(result, offset, limit))
    return _run(_search())


@tool
def ppubs_search_applications(query: str, offset: int = 0, limit: int = 100, sort: str = "date_publ desc") -> Dict[str, Any]:
    """Search published US patent applications via PPUBS.

    Args:
        query: USPTO search syntax (same as ppubs_search_patents)
        offset: Pagination start (default 0)
        limit: Max results (default 100, max 500)
        sort: Sort order (default "date_publ desc")
    """
    async def _search():
        result = await _client.run_query(query=query, start=offset, limit=min(limit, 500), sort=sort, sources=[Sources.PUBLISHED_APPLICATIONS])
        if is_error(result):
            return result
        return check_and_truncate(ResponseEnvelope.from_ppubs(result, offset, limit))
    return _run(_search())


@tool
def ppubs_get_full_document(guid: str, source_type: str) -> Dict[str, Any]:
    """Get complete patent document by GUID.

    Args:
        guid: Document GUID (e.g. "US-9876543-B2")
        source_type: "USPAT" for patents, "US-PGPUB" for applications
    """
    async def _get():
        result = await _client.get_document(guid, source_type)
        if is_error(result):
            return result
        return check_and_truncate(result)
    return _run(_get())


@tool
def ppubs_get_patent_by_number(patent_number: str) -> Dict[str, Any]:
    """Get a granted patent's full text by patent number.

    Args:
        patent_number: Patent number without commas (e.g. "7123456")
    """
    async def _get():
        try:
            pn = validate_patent_number(str(patent_number))
        except ValueError as e:
            return ApiError.validation_error(str(e), "patent_number")
        search_result = await _search_patent_by_number(pn)
        if is_error(search_result):
            return search_result
        patent = search_result["patent"]
        result = await _client.get_document(patent[Fields.GUID], patent[Fields.TYPE])
        if is_error(result):
            return result
        return check_and_truncate(result)
    return _run(_get())


@tool
def ppubs_download_patent_pdf(patent_number: str) -> Dict[str, Any]:
    """Download a patent as PDF (base64 encoded).

    Args:
        patent_number: Patent number without commas (e.g. "7123456")
    """
    async def _get():
        try:
            pn = validate_patent_number(str(patent_number))
        except ValueError as e:
            return ApiError.validation_error(str(e), "patent_number")
        search_result = await _search_patent_by_number(pn)
        if is_error(search_result):
            return search_result
        patent = search_result["patent"]
        # Fetch document to get imageLocation and pageCount needed for PDF
        doc = await _client.get_document(patent[Fields.GUID], patent[Fields.TYPE])
        if is_error(doc):
            return doc
        image_location = doc.get(Fields.IMAGE_LOCATION)
        page_count = doc.get(Fields.PAGE_COUNT)
        if not image_location or not page_count:
            return ApiError.create("Document missing image metadata for PDF download")
        return await _client.download_image(patent[Fields.GUID], image_location, page_count, patent[Fields.TYPE])
    return _run(_get())


ALL_TOOLS = [
    check_api_status,
    get_cpc_info,
    get_status_code,
    ppubs_search_patents,
    ppubs_search_applications,
    ppubs_get_full_document,
    ppubs_get_patent_by_number,
    ppubs_download_patent_pdf,
]
