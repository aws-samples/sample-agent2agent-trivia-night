"""
Agent service for CRUD operations against S3 Vectors.

Stores agent cards as vector metadata alongside embeddings generated from
agent name, description, and skills via Bedrock Titan Text Embeddings V2.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from services.embedding_service import EmbeddingService, EmbeddingServiceError
from utils.logging import get_logger
from utils.validation import ValidationError, validate_agent_card, validate_agent_id

logger = get_logger(__name__)


class AgentNotFoundError(Exception):
    """Raised when an agent cannot be found in the registry."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.message = f"Agent with ID {agent_id} not found"
        super().__init__(self.message)


class AgentServiceError(Exception):
    """Custom exception for agent service errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "AGENT_SERVICE_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class AgentService:
    """Service for managing agent cards in S3 Vectors."""

    def __init__(
        self,
        vector_bucket_name: Optional[str] = None,
        index_name: Optional[str] = None,
    ) -> None:
        """Initialise the agent service.

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
                f"Initialised AgentService bucket={self.vector_bucket_name} "
                f"index={self.index_name}"
            )
        except Exception as e:
            logger.warning(f"Failed to initialise AgentService: {e}")
            raise AgentServiceError(
                f"Failed to initialise services: {e}", "INITIALIZATION_ERROR"
            )

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create_agent(self, agent_card: Dict[str, Any]) -> str:
        """Create a new agent and store it in S3 Vectors.

        Args:
            agent_card: Raw agent card payload.  Must contain ``name``,
                ``description``, and ``url``.

        Returns:
            The generated UUID v4 agent ID.

        Raises:
            ValidationError: If the payload is invalid.
            AgentServiceError: If storage or embedding generation fails.
        """
        logger.info("Creating new agent")

        # Validate required fields
        validate_agent_card(agent_card)

        agent_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Build embedding text from name + description + skills
        skills_list: List[Dict[str, Any]] = agent_card.get("skills", [])
        embedding_text = EmbeddingService.build_embedding_text(
            name=agent_card.get("name", ""),
            description=agent_card.get("description", ""),
            skills=skills_list,
        )

        try:
            embedding_vector = self.embedding_service.generate_embedding(embedding_text)
        except EmbeddingServiceError as e:
            logger.warning(f"Embedding generation failed for new agent: {e}")
            raise AgentServiceError(
                f"Failed to generate embedding: {e}",
                "EMBEDDING_GENERATION_ERROR",
                {"agent_id": agent_id},
            )

        # Extract skill names as flat string list for S3 Vectors filtering
        skill_names = [
            s.get("name", "")
            for s in skills_list
            if isinstance(s, dict) and s.get("name")
        ]

        metadata = {
            "agent_id": agent_id,
            "name": agent_card.get("name"),
            "description": agent_card.get("description"),
            "url": agent_card.get("url"),
            "skills": skill_names,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "is_online": False,
            "last_health_check": "",
            "raw_agent_card": json.dumps(agent_card),
        }

        try:
            self.s3vectors_client.put_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                vectors=[
                    {
                        "key": f"agent-{agent_id}",
                        "data": {"float32": embedding_vector},
                        "metadata": metadata,
                    }
                ],
            )
            logger.info(f"Agent created agent_id={agent_id}")
            return agent_id

        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "UNKNOWN")
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.warning(f"S3 Vectors put_vectors failed [{code}]: {msg}")
            raise AgentServiceError(
                f"Failed to store agent: {msg}",
                "STORAGE_ERROR",
                {"agent_id": agent_id, "aws_error_code": code},
            )
        except Exception as e:
            logger.warning(f"Unexpected error creating agent: {e}")
            raise AgentServiceError(f"Unexpected error creating agent: {e}")

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """Retrieve an agent card by ID.

        Args:
            agent_id: The agent identifier.

        Returns:
            The agent card dict (including ``agent_id``, timestamps, etc.).

        Raises:
            ValidationError: If *agent_id* is invalid.
            AgentNotFoundError: If no agent with the given ID exists.
            AgentServiceError: On storage errors.
        """
        logger.info(f"Retrieving agent agent_id={agent_id}")
        validate_agent_id(agent_id)

        try:
            response = self.s3vectors_client.get_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                keys=[f"agent-{agent_id}"],
                returnMetadata=True,
            )

            vectors = response.get("vectors", [])
            if not vectors:
                logger.info(f"Agent not found agent_id={agent_id}")
                raise AgentNotFoundError(agent_id)

            metadata = vectors[0].get("metadata", {})
            raw_card = metadata.get("raw_agent_card")
            if not raw_card:
                logger.warning(f"Agent missing raw_agent_card agent_id={agent_id}")
                raise AgentNotFoundError(agent_id)

            agent_data: Dict[str, Any] = json.loads(raw_card)
            # Enrich with registry metadata
            agent_data["agent_id"] = metadata.get("agent_id", agent_id)
            agent_data["created_at"] = metadata.get("created_at", "")
            agent_data["updated_at"] = metadata.get("updated_at", "")
            agent_data["is_online"] = metadata.get("is_online", False)
            agent_data["last_health_check"] = metadata.get("last_health_check", "")

            logger.info(f"Agent retrieved agent_id={agent_id}")
            return agent_data

        except AgentNotFoundError:
            raise
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "UNKNOWN")
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.warning(f"S3 Vectors get_vectors failed [{code}]: {msg}")
            raise AgentServiceError(
                f"Failed to retrieve agent: {msg}",
                "RETRIEVAL_ERROR",
                {"agent_id": agent_id, "aws_error_code": code},
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted agent data agent_id={agent_id}: {e}")
            raise AgentServiceError(
                f"Corrupted agent data: {e}", "DATA_CORRUPTION_ERROR"
            )
        except Exception as e:
            logger.warning(f"Unexpected error retrieving agent: {e}")
            raise AgentServiceError(f"Unexpected error retrieving agent: {e}")

    # ------------------------------------------------------------------
    # LIST
    # ------------------------------------------------------------------

    def list_agents(
        self, limit: int = 50, offset: int = 0
    ) -> Dict[str, Any]:
        """List agents with pagination.

        Args:
            limit: Maximum number of agents to return.
            offset: Number of agents to skip.

        Returns:
            Dict with ``items`` (list of agent cards) and ``pagination``
            metadata.

        Raises:
            AgentServiceError: On storage errors.
        """
        logger.info(f"Listing agents limit={limit} offset={offset}")

        try:
            response = self.s3vectors_client.list_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                maxResults=1000,
                returnMetadata=True,
            )

            vectors = response.get("vectors", [])

            # Keep only agent vectors
            agent_vectors = [
                v for v in vectors if v.get("key", "").startswith("agent-")
            ]

            # Sort newest first
            agent_vectors.sort(
                key=lambda v: v.get("metadata", {}).get("created_at", ""),
                reverse=True,
            )

            total = len(agent_vectors)
            page = agent_vectors[offset : offset + limit]

            items: List[Dict[str, Any]] = []
            for vector in page:
                metadata = vector.get("metadata", {})
                raw_card = metadata.get("raw_agent_card")
                if not raw_card:
                    continue
                try:
                    agent_data = json.loads(raw_card)
                    agent_data["agent_id"] = metadata.get("agent_id")
                    agent_data["created_at"] = metadata.get("created_at", "")
                    agent_data["updated_at"] = metadata.get("updated_at", "")
                    agent_data["is_online"] = metadata.get("is_online", False)
                    agent_data["last_health_check"] = metadata.get(
                        "last_health_check", ""
                    )
                    items.append(agent_data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Skipping corrupted agent agent_id={metadata.get('agent_id')}"
                    )

            has_more = (offset + limit) < total

            result = {
                "items": items,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": total,
                    "has_more": has_more,
                },
            }
            logger.info(f"Listed {len(items)} agents total={total}")
            return result

        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "UNKNOWN")
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.warning(f"S3 Vectors list_vectors failed [{code}]: {msg}")
            raise AgentServiceError(
                f"Failed to list agents: {msg}",
                "LISTING_ERROR",
                {"aws_error_code": code},
            )
        except Exception as e:
            logger.warning(f"Unexpected error listing agents: {e}")
            raise AgentServiceError(f"Unexpected error listing agents: {e}")


    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update_agent(
        self, agent_id: str, agent_card: Dict[str, Any]
    ) -> bool:
        """Update an existing agent card.

        Merges *agent_card* into the existing record, re-validates, and
        regenerates the embedding if name or description changed.

        Args:
            agent_id: The agent identifier.
            agent_card: Partial or full updated agent card data.

        Returns:
            ``True`` on success.

        Raises:
            ValidationError: If the merged data is invalid.
            AgentNotFoundError: If the agent does not exist.
            AgentServiceError: On storage or embedding errors.
        """
        logger.info(f"Updating agent agent_id={agent_id}")
        validate_agent_id(agent_id)

        # Fetch existing agent (raises AgentNotFoundError if missing)
        existing = self.get_agent(agent_id)

        # Merge updates into existing data
        merged = existing.copy()
        merged.update(agent_card)

        # Re-validate the merged card
        validate_agent_card(merged)

        now = datetime.now(timezone.utc)
        skills_list: List[Dict[str, Any]] = merged.get("skills", [])
        skill_names = [
            s.get("name", "")
            for s in skills_list
            if isinstance(s, dict) and s.get("name")
        ]

        # Determine whether we need a new embedding
        name_changed = existing.get("name") != merged.get("name")
        desc_changed = existing.get("description") != merged.get("description")
        skills_changed = existing.get("skills") != merged.get("skills")

        if name_changed or desc_changed or skills_changed:
            embedding_text = EmbeddingService.build_embedding_text(
                name=merged.get("name", ""),
                description=merged.get("description", ""),
                skills=skills_list,
            )
            try:
                embedding_vector = self.embedding_service.generate_embedding(
                    embedding_text
                )
            except EmbeddingServiceError as e:
                logger.warning(f"Embedding generation failed during update: {e}")
                raise AgentServiceError(
                    f"Failed to generate embedding: {e}",
                    "EMBEDDING_GENERATION_ERROR",
                    {"agent_id": agent_id},
                )
        else:
            # Retrieve existing embedding
            try:
                vec_resp = self.s3vectors_client.get_vectors(
                    vectorBucketName=self.vector_bucket_name,
                    indexName=self.index_name,
                    keys=[f"agent-{agent_id}"],
                    returnData=True,
                )
                vectors = vec_resp.get("vectors", [])
                if not vectors:
                    raise AgentServiceError(
                        f"Could not find existing vector for agent {agent_id}",
                        "VECTOR_NOT_FOUND",
                    )
                embedding_vector = vectors[0].get("data", {}).get("float32", [])
                if not embedding_vector:
                    raise AgentServiceError(
                        f"Invalid embedding data for agent {agent_id}",
                        "INVALID_EMBEDDING_DATA",
                    )
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "UNKNOWN")
                msg = e.response.get("Error", {}).get("Message", str(e))
                logger.warning(f"Failed to retrieve existing embedding: {msg}")
                raise AgentServiceError(
                    f"Failed to retrieve existing embedding: {msg}",
                    "EMBEDDING_RETRIEVAL_ERROR",
                    {"agent_id": agent_id, "aws_error_code": code},
                )

        metadata = {
            "agent_id": agent_id,
            "name": merged.get("name"),
            "description": merged.get("description"),
            "url": merged.get("url"),
            "skills": skill_names,
            "created_at": existing.get("created_at", now.isoformat()),
            "updated_at": now.isoformat(),
            "is_online": existing.get("is_online", False),
            "last_health_check": existing.get("last_health_check", ""),
            "raw_agent_card": json.dumps(merged),
        }

        try:
            self.s3vectors_client.put_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                vectors=[
                    {
                        "key": f"agent-{agent_id}",
                        "data": {"float32": embedding_vector},
                        "metadata": metadata,
                    }
                ],
            )
            logger.info(
                f"Agent updated agent_id={agent_id} "
                f"embedding_regenerated={name_changed or desc_changed or skills_changed}"
            )
            return True

        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "UNKNOWN")
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.warning(f"S3 Vectors put_vectors failed during update [{code}]: {msg}")
            raise AgentServiceError(
                f"Failed to update agent: {msg}",
                "UPDATE_ERROR",
                {"agent_id": agent_id, "aws_error_code": code},
            )
        except Exception as e:
            logger.warning(f"Unexpected error updating agent: {e}")
            raise AgentServiceError(f"Unexpected error updating agent: {e}")

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete_agent(self, agent_id: str) -> bool:
        """Remove an agent from S3 Vectors.

        Args:
            agent_id: The agent identifier.

        Returns:
            ``True`` on success.

        Raises:
            ValidationError: If *agent_id* is invalid.
            AgentNotFoundError: If the agent does not exist.
            AgentServiceError: On storage errors.
        """
        logger.info(f"Deleting agent agent_id={agent_id}")
        validate_agent_id(agent_id)

        # Verify the agent exists first (raises AgentNotFoundError if not)
        self.get_agent(agent_id)

        try:
            self.s3vectors_client.delete_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                keys=[f"agent-{agent_id}"],
            )
            logger.info(f"Agent deleted agent_id={agent_id}")
            return True

        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "UNKNOWN")
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.warning(f"S3 Vectors delete_vectors failed [{code}]: {msg}")
            raise AgentServiceError(
                f"Failed to delete agent: {msg}",
                "DELETION_ERROR",
                {"agent_id": agent_id, "aws_error_code": code},
            )
        except Exception as e:
            logger.warning(f"Unexpected error deleting agent: {e}")
            raise AgentServiceError(f"Unexpected error deleting agent: {e}")
