"""
Health service for updating agent online status and last-seen timestamps.

Delegates agent existence checks to :class:`AgentService` and updates
the vector metadata in S3 Vectors with the current timestamp and
``is_online=True``.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from services.agent_service import AgentNotFoundError, AgentService
from utils.logging import get_logger

logger = get_logger(__name__)


class HealthServiceError(Exception):
    """Raised when a health-check update fails."""

    def __init__(
        self,
        message: str,
        error_code: str = "HEALTH_SERVICE_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class HealthService:
    """Manages agent health-check updates in S3 Vectors."""

    def __init__(
        self,
        vector_bucket_name: Optional[str] = None,
        index_name: Optional[str] = None,
        agent_service: Optional[AgentService] = None,
    ) -> None:
        self.vector_bucket_name = vector_bucket_name or os.environ.get(
            "S3_VECTORS_BUCKET", "agent-registry-vectors"
        )
        self.index_name = index_name or os.environ.get(
            "S3_VECTORS_INDEX", "agent-embeddings"
        )

        self.agent_service = agent_service or AgentService(
            vector_bucket_name=self.vector_bucket_name,
            index_name=self.index_name,
        )

        try:
            region = os.environ.get("AWS_REGION", "us-east-1")
            self.s3vectors_client = boto3.client("s3vectors", region_name=region)
            logger.info(
                f"Initialised HealthService bucket={self.vector_bucket_name} "
                f"index={self.index_name}"
            )
        except Exception as e:
            logger.error(f"Failed to initialise HealthService: {e}")
            raise HealthServiceError(
                f"Failed to initialise health service: {e}",
                "INITIALIZATION_ERROR",
            )

    def update_health(self, agent_id: str) -> Dict[str, Any]:
        """Update an agent's health-check timestamp and set it online.

        Verifies the agent exists via :meth:`AgentService.get_agent`, then
        updates the vector metadata with the current UTC timestamp for
        ``last_health_check`` and sets ``is_online`` to ``True``.

        Args:
            agent_id: The agent identifier.

        Returns:
            A dict with ``agent_id``, ``is_online``, and
            ``last_health_check`` fields.

        Raises:
            AgentNotFoundError: If no agent with *agent_id* exists.
            HealthServiceError: On storage errors.
        """
        logger.info(f"Updating health for agent_id={agent_id}")

        # Verify agent exists — raises AgentNotFoundError if missing
        self.agent_service.get_agent(agent_id)

        now = datetime.now(timezone.utc)

        try:
            # Fetch the existing vector (need data + metadata for put_vectors)
            response = self.s3vectors_client.get_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                keys=[f"agent-{agent_id}"],
                returnMetadata=True,
                returnData=True,
            )

            vectors = response.get("vectors", [])
            if not vectors:
                raise AgentNotFoundError(agent_id)

            vector = vectors[0]
            metadata = vector.get("metadata", {})
            embedding_data = vector.get("data", {})

            # Update health fields
            metadata["last_health_check"] = now.isoformat()
            metadata["is_online"] = True
            metadata["updated_at"] = now.isoformat()

            # Also update the raw_agent_card JSON if present
            raw_card = metadata.get("raw_agent_card")
            if raw_card:
                try:
                    card = json.loads(raw_card)
                    card["last_health_check"] = now.isoformat()
                    card["is_online"] = True
                    metadata["raw_agent_card"] = json.dumps(card)
                except (json.JSONDecodeError, TypeError):
                    pass  # leave raw_agent_card as-is if unparseable

            # Write back with updated metadata
            self.s3vectors_client.put_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                vectors=[
                    {
                        "key": f"agent-{agent_id}",
                        "data": embedding_data,
                        "metadata": metadata,
                    }
                ],
            )

            result = {
                "agent_id": agent_id,
                "is_online": True,
                "last_health_check": now.isoformat(),
            }
            logger.info(
                f"Health updated agent_id={agent_id} "
                f"last_health_check={now.isoformat()}"
            )
            return result

        except AgentNotFoundError:
            raise
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "UNKNOWN")
            msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(
                f"S3 Vectors health update failed [{code}]: {msg}"
            )
            raise HealthServiceError(
                f"Failed to update agent health: {msg}",
                "HEALTH_UPDATE_ERROR",
                {"agent_id": agent_id, "aws_error_code": code},
            )
        except Exception as e:
            logger.error(f"Unexpected error updating health: {e}")
            raise HealthServiceError(
                f"Unexpected error updating agent health: {e}",
                "HEALTH_UPDATE_ERROR",
            )
