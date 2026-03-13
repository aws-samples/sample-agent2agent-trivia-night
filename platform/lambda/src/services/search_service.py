"""
Search service for semantic and skill-based agent search.

Uses Bedrock Titan Text Embeddings V2 to generate query embeddings and
S3 Vectors cosine similarity queries to find matching agents.
"""
import json
import os
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from services.embedding_service import EmbeddingService, EmbeddingServiceError
from utils.logging import get_logger

logger = get_logger(__name__)


class SearchServiceError(Exception):
    """Base exception for search service errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "SEARCH_SERVICE_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class SearchService:
    """Service for searching agents using S3 Vectors cosine similarity."""

    def __init__(
        self,
        vector_bucket_name: Optional[str] = None,
        index_name: Optional[str] = None,
    ) -> None:
        """Initialise the search service.

        Args:
            vector_bucket_name: S3 Vectors bucket name.  Falls back to the
                ``S3_VECTORS_BUCKET`` environment variable.
            index_name: S3 Vectors index name.  Falls back to the
                ``S3_VECTORS_INDEX`` environment variable.
        """
        self.vector_bucket_name = vector_bucket_name or os.environ.get(
            "S3_VECTORS_BUCKET", "agent-registry-vectors"
        )
        self.index_name = index_name or os.environ.get(
            "S3_VECTORS_INDEX", "agent-embeddings"
        )

        try:
            region = os.environ.get("AWS_REGION", "us-east-1")
            self.s3vectors_client = boto3.client("s3vectors", region_name=region)
            self.embedding_service = EmbeddingService(region_name=region)
            logger.info(
                f"Initialised SearchService bucket={self.vector_bucket_name} "
                f"index={self.index_name}"
            )
        except Exception as e:
            logger.warning(f"Failed to initialise SearchService: {e}")
            raise SearchServiceError(
                f"Failed to initialise search service: {e}", "INITIALIZATION_ERROR"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_skill_matches(
        self, agent_skills: List[str], query_skills: Optional[List[str]]
    ) -> List[str]:
        """Return the intersection of *agent_skills* and *query_skills*.

        Comparison is case-insensitive.  The returned list preserves the
        original casing from *agent_skills*.
        """
        if not query_skills:
            return []

        query_lower = {s.lower() for s in query_skills}
        return [s for s in agent_skills if s.lower() in query_lower]

    def _parse_agent_skills(self, metadata: Dict[str, Any]) -> List[str]:
        """Extract the skills list from vector metadata.

        Skills may be stored as a JSON-encoded string or a native list.
        """
        raw = metadata.get("skills", [])
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(raw, list):
            return raw
        return []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_agents(
        self,
        query: Optional[str] = None,
        skills: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """Search for agents by semantic query and/or skills filter.

        At least one of *query* or *skills* must be provided.

        Args:
            query: Free-text search query for semantic similarity.
            skills: Optional list of skill names to filter results by.
                Results must have at least one overlapping skill.
            top_k: Maximum number of results to return (capped at 30 by
                S3 Vectors).

        Returns:
            A dict with the structure::

                {
                    "results": [
                        {
                            "agent_id": "...",
                            "agent_card": { ... },
                            "similarity_score": 0.95,
                            "matched_skills": ["skill1"]
                        }
                    ],
                    "query": {"text": "...", "skills": [...]},
                    "count": 5
                }

        Raises:
            SearchServiceError: If the search operation fails.
        """
        if not query and not skills:
            raise SearchServiceError(
                "Either query text or skills must be provided",
                "INVALID_SEARCH_PARAMS",
            )

        # For skills-only searches, use a generic query to get embeddings
        search_text = query.strip() if query else "Agent"

        logger.info(
            f"Searching agents query={search_text!r} skills={skills} top_k={top_k}"
        )

        try:
            # 1. Generate embedding from query text
            try:
                query_embedding = self.embedding_service.generate_embedding(search_text)
            except EmbeddingServiceError as e:
                logger.warning(f"Failed to generate query embedding: {e}")
                raise SearchServiceError(
                    f"Failed to generate query embedding: {e}", "EMBEDDING_ERROR"
                )

            # 2. Query S3 Vectors using cosine similarity
            query_params: Dict[str, Any] = {
                "vectorBucketName": self.vector_bucket_name,
                "indexName": self.index_name,
                "queryVector": {"float32": query_embedding},
                "topK": min(top_k, 30),
                "returnDistance": True,
                "returnMetadata": True,
            }

            response = self.s3vectors_client.query_vectors(**query_params)
            vectors = response.get("vectors", [])

            logger.info(f"S3 Vectors returned {len(vectors)} results")

            # 3. Process results, apply skills filter, and rank
            results: List[Dict[str, Any]] = []

            for vector in vectors:
                try:
                    metadata = vector.get("metadata", {})
                    distance = vector.get("distance", 1.0)

                    # Similarity = 1 - cosine distance
                    similarity_score = max(0.0, 1.0 - distance)

                    # Parse the raw agent card
                    raw_card = metadata.get("raw_agent_card")
                    if not raw_card:
                        logger.warning(
                            f"Skipping result with missing agent card: "
                            f"agent_id={metadata.get('agent_id')}"
                        )
                        continue

                    try:
                        agent_card = json.loads(raw_card)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Skipping result with corrupted agent card: "
                            f"agent_id={metadata.get('agent_id')} error={e}"
                        )
                        continue

                    # Calculate skill matches
                    agent_skills = self._parse_agent_skills(metadata)
                    matched_skills = self._calculate_skill_matches(
                        agent_skills, skills
                    )

                    # 4. Filter by skills overlap if skills filter provided
                    if skills and not matched_skills:
                        continue

                    results.append(
                        {
                            "agent_id": metadata.get("agent_id", ""),
                            "agent_card": agent_card,
                            "similarity_score": round(similarity_score, 6),
                            "matched_skills": matched_skills,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Error processing search result: {e}")
                    continue

            # 5. Sort by similarity_score descending
            results.sort(key=lambda r: r["similarity_score"], reverse=True)

            logger.info(
                f"Search complete: {len(results)} results after filtering"
            )

            return {
                "results": results,
                "query": {
                    "text": query or "",
                    "skills": skills or [],
                },
                "count": len(results),
            }

        except SearchServiceError:
            raise
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "UNKNOWN")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.warning(
                f"S3 Vectors query failed [{error_code}]: {error_msg}"
            )
            raise SearchServiceError(
                f"Vector search failed: {error_msg}",
                "VECTOR_SEARCH_ERROR",
                {"aws_error_code": error_code},
            )
        except Exception as e:
            logger.warning(f"Unexpected error during search: {e}")
            raise SearchServiceError(
                f"Unexpected search error: {e}", "SEARCH_ERROR"
            )
