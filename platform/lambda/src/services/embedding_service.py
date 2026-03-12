"""
Embedding service for generating text embeddings using Bedrock Titan Text Embeddings V2.
"""
import json
import logging
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)


class EmbeddingServiceError(Exception):
    """Base exception for embedding service errors."""
    pass


class BedrockAPIError(EmbeddingServiceError):
    """Exception raised when Bedrock API calls fail."""
    pass


class TextPreprocessingError(EmbeddingServiceError):
    """Exception raised when text preprocessing fails."""
    pass


class EmbeddingService:
    """Service for generating embeddings using AWS Bedrock Titan Text Embeddings V2."""

    MODEL_ID = "amazon.titan-embed-text-v2:0"
    MAX_INPUT_CHARACTERS = 50000
    OUTPUT_DIMENSION = 1024

    def __init__(self, region_name: Optional[str] = None):
        """
        Initialize the embedding service.

        Args:
            region_name: AWS region name. If None, uses default region.
        """
        try:
            self.bedrock_client = boto3.client(
                "bedrock-runtime",
                region_name=region_name,
            )
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            raise EmbeddingServiceError(f"Failed to initialize Bedrock client: {e}")

    @staticmethod
    def build_embedding_text(name: str, description: str, skills: list) -> str:
        """
        Build the text input for embedding generation by concatenating agent fields.

        Args:
            name: Agent name.
            description: Agent description.
            skills: List of skill dicts (with 'name' and optional 'description' keys)
                    or plain strings.

        Returns:
            Concatenated text suitable for embedding generation.
        """
        parts = [name or "", description or ""]
        for skill in skills or []:
            if isinstance(skill, dict):
                parts.append(skill.get("name", ""))
                parts.append(skill.get("description", ""))
            else:
                parts.append(str(skill))
        return " ".join(p for p in parts if p)

    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text for embedding generation.

        Args:
            text: Raw text to preprocess.

        Returns:
            Preprocessed text ready for embedding.

        Raises:
            TextPreprocessingError: If text is empty or invalid.
        """
        if not text or not isinstance(text, str):
            raise TextPreprocessingError("Text must be a non-empty string")

        processed = text.strip()
        if not processed:
            raise TextPreprocessingError("Text cannot be empty after preprocessing")

        if len(processed) > self.MAX_INPUT_CHARACTERS:
            logger.warning(
                f"Text length ({len(processed)}) exceeds maximum "
                f"({self.MAX_INPUT_CHARACTERS}). Truncating."
            )
            processed = processed[: self.MAX_INPUT_CHARACTERS]

        return processed

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate a 1024-dimension embedding for the given text using Bedrock
        Titan Text Embeddings V2.

        Args:
            text: Text to generate embedding for.

        Returns:
            List of 1024 float values representing the embedding vector.

        Raises:
            TextPreprocessingError: If text preprocessing fails.
            BedrockAPIError: If the Bedrock API call fails.
            EmbeddingServiceError: For other unexpected errors.
        """
        try:
            processed_text = self.preprocess_text(text)

            request_body = {"inputText": processed_text}

            logger.debug(f"Generating embedding for text length: {len(processed_text)}")

            response = self.bedrock_client.invoke_model(
                modelId=self.MODEL_ID,
                body=json.dumps(request_body),
            )

            response_body = json.loads(response["body"].read())

            if "embedding" not in response_body:
                raise BedrockAPIError("No embedding found in Bedrock response")

            embedding = response_body["embedding"]

            if len(embedding) != self.OUTPUT_DIMENSION:
                raise BedrockAPIError(
                    f"Unexpected embedding dimension: {len(embedding)}, "
                    f"expected: {self.OUTPUT_DIMENSION}"
                )

            logger.debug(f"Successfully generated {len(embedding)}-dim embedding")
            return embedding

        except (TextPreprocessingError, BedrockAPIError):
            raise
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"Bedrock API error [{error_code}]: {error_message}")
            raise BedrockAPIError(f"Bedrock API error [{error_code}]: {error_message}")
        except BotoCoreError as e:
            logger.error(f"Boto3 client error: {e}")
            raise BedrockAPIError(f"Boto3 client error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bedrock response: {e}")
            raise BedrockAPIError(f"Failed to parse Bedrock response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during embedding generation: {e}")
            raise EmbeddingServiceError(
                f"Unexpected error during embedding generation: {e}"
            )

    def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to generate embeddings for.

        Returns:
            List of embedding vectors (None for any that failed).
        """
        if not texts:
            return []

        embeddings: List[Optional[List[float]]] = []
        failed_indices = []

        for i, text in enumerate(texts):
            try:
                embeddings.append(self.generate_embedding(text))
            except Exception as e:
                logger.error(f"Failed to generate embedding for text {i}: {e}")
                failed_indices.append(i)
                embeddings.append(None)

        if failed_indices:
            logger.warning(
                f"Failed to generate embeddings for {len(failed_indices)} texts"
            )

        return embeddings
