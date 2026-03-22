"""
Drug Information Tools

This module provides tools for querying FDA-approved drug information
from the OpenFDA API.
"""

import httpx
from typing import Optional, Dict, Any, List
import logging
import urllib.parse
from strands import tool

logger = logging.getLogger(__name__)


@tool
def get_approved_drugs(
    condition: str,
    route: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Query FDA database for approved drugs.
    
    This function searches the OpenFDA drugsfda API for approved drugs
    based on condition (indication) and optionally filters by route of
    administration. Results are summarized with total drug count, route
    breakdown, and example drug names.
    
    Args:
        condition: Disease or indication to search for (e.g., "diabetes", "hypertension")
        route: Optional route of administration (e.g., "oral", "nasal", "intravenous")
        limit: Maximum number of results to retrieve (default: 100, max: 1000)
    
    Returns:
        Dictionary containing drug information summary with the following structure:
        {
            "total_drugs": int,           # Number of unique drugs found
            "routes": {                   # Breakdown by route of administration
                "ORAL": int,
                "INTRAVENOUS": int,
                ...
            },
            "drug_names": [str, ...]      # List of up to 10 example drug names
        }
    
    Raises:
        ValueError: If required parameters are missing or invalid
        Exception: If the API request fails
    """
    # Validate required parameters
    if not condition:
        raise ValueError("condition is required")
    
    # Validate limit
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    
    base_url = "https://api.fda.gov/drug/drugsfda.json"
    
    # Build search query with proper sanitization
    search_terms = []
    
    # Sanitize condition parameter
    # OpenFDA API requires spaces and special characters to be handled properly
    sanitized_condition = _sanitize_query_parameter(condition)
    search_terms.append(f'openfda.brand_name:{sanitized_condition}')
    
    # Add route filter if provided
    if route:
        sanitized_route = _sanitize_query_parameter(route)
        search_terms.append(f'openfda.route:{sanitized_route}')
    
    # Combine search terms with AND
    search_query = '+AND+'.join(search_terms)
    
    params = {
        'search': search_query,
        'limit': limit
    }
    
    try:
        logger.info(f"Querying OpenFDA for drugs with condition: {condition}, route: {route}")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])
            
            # Process and summarize results
            summary = _summarize_drug_results(results)
            
            logger.info(f"Found {summary['total_drugs']} unique drugs for condition: {condition}")
            
            return summary
    
    except httpx.TimeoutException as e:
        logger.error(f"Timeout while querying OpenFDA: {e}")
        raise Exception("The OpenFDA API request timed out. Please try again.") from e
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.info(f"No drugs found for condition: {condition}")
            return {
                "total_drugs": 0,
                "routes": {},
                "drug_names": []
            }
        elif e.response.status_code == 429:
            logger.error(f"Rate limit exceeded for OpenFDA API")
            raise Exception("OpenFDA API rate limit exceeded. Please try again later.") from e
        else:
            logger.error(f"HTTP error while querying OpenFDA: {e}")
            raise Exception(f"Failed to query OpenFDA: {e.response.status_code} {e.response.reason_phrase}") from e
    
    except httpx.RequestError as e:
        logger.error(f"Request error while querying OpenFDA: {e}")
        raise Exception("Failed to connect to OpenFDA API. Please check your network connection.") from e
    
    except Exception as e:
        logger.error(f"Unexpected error while querying OpenFDA: {e}")
        raise Exception(f"An unexpected error occurred while querying drug information: {str(e)}") from e


def _sanitize_query_parameter(param: str) -> str:
    """
    Sanitize query parameters for OpenFDA API.
    
    The OpenFDA API requires special handling for spaces and special characters:
    - Multi-word terms should be quoted
    - Special characters should be URL-encoded
    
    Args:
        param: Raw parameter string
    
    Returns:
        Sanitized parameter string safe for API consumption
    """
    if not param:
        return param
    
    # Trim whitespace
    param = param.strip()
    
    # If parameter contains spaces, wrap in quotes
    if ' ' in param:
        # Escape any existing quotes
        param = param.replace('"', '\\"')
        param = f'"{param}"'
    
    # URL encode the parameter to handle special characters
    # Note: We don't encode the quotes we just added
    return param


def _summarize_drug_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Summarize drug query results.
    
    Processes raw OpenFDA API results to extract:
    - Total count of unique drugs
    - Breakdown by route of administration
    - Example drug names (up to 10)
    
    Args:
        results: List of drug records from OpenFDA API
    
    Returns:
        Dictionary with summary statistics
    """
    unique_drugs = set()
    route_counts: Dict[str, int] = {}
    
    for item in results:
        # Extract products from each drug record
        products = item.get("products", [])
        
        for product in products:
            # Get brand name
            brand_name = product.get("brand_name")
            if brand_name:
                unique_drugs.add(brand_name)
            
            # Get route of administration
            route = product.get("route")
            if route:
                # Route can be a list or a single value
                if isinstance(route, list):
                    for r in route:
                        route_counts[r] = route_counts.get(r, 0) + 1
                else:
                    route_counts[route] = route_counts.get(route, 0) + 1
    
    # Get up to 10 example drug names
    drug_names_list = sorted(list(unique_drugs))[:10]
    
    return {
        "total_drugs": len(unique_drugs),
        "routes": route_counts,
        "drug_names": drug_names_list
    }
