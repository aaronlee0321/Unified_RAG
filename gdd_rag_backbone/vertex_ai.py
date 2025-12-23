"""
Vertex AI integration module for embeddings.

This module provides:
- Embedding generation using Vertex AI text-embedding-004

All Vertex AI-specific logic is contained here.
"""

import os
import json
import logging
from typing import List
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy initialization - only initialize when first used
_vertex_initialized = False
_embedding_model = None


def _initialize_vertex_ai():
    """Initialize Vertex AI client (lazy initialization)."""
    global _vertex_initialized, _embedding_model
    
    if _vertex_initialized:
        return
    
    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel
        
        project_id = os.getenv("VERTEX_PROJECT_ID")
        location = os.getenv("VERTEX_LOCATION", "us-central1")
        
        if not project_id:
            raise ValueError("VERTEX_PROJECT_ID environment variable must be set")
        
        vertexai.init(project=project_id, location=location)
        
        # Initialize embedding model
        embedding_model_name = os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-004")
        _embedding_model = TextEmbeddingModel.from_pretrained(embedding_model_name)
        
        _vertex_initialized = True
        logger.info(f"Vertex AI initialized: project={project_id}, location={location}")
        
    except ImportError:
        logger.warning("vertexai package not installed. Install with: pip install google-cloud-aiplatform")
        raise
    except Exception as e:
        logger.error(f"Failed to initialize Vertex AI: {e}")
        raise


def embed_text(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings using Vertex AI text-embedding-004.
    
    Args:
        texts: List of text strings to embed
        
    Returns:
        List of embedding vectors (768 dimensions for text-embedding-004)
        
    Raises:
        ValueError: If Vertex AI is not properly configured
        RuntimeError: If embedding generation fails
    """
    if not texts:
        return []
    
    _initialize_vertex_ai()
    
    if _embedding_model is None:
        raise RuntimeError("Vertex AI embedding model not initialized")
    
    try:
        # Vertex AI supports batch requests (up to 5 texts per request)
        # Process in batches to handle large lists efficiently
        batch_size = 5
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = _embedding_model.get_embeddings(batch)
            
            # Convert to list of lists
            for embedding in embeddings:
                # Extract values from embedding object
                if hasattr(embedding, 'values'):
                    all_embeddings.append(list(embedding.values))
                elif isinstance(embedding, list):
                    all_embeddings.append(list(embedding))
                else:
                    # Fallback: try to convert to list
                    all_embeddings.append([float(x) for x in embedding])
        
        # Detect and log dimension on first use
        if all_embeddings and not hasattr(embed_text, '_dimension_logged'):
            dim = len(all_embeddings[0])
            logger.info(f"Vertex AI embeddings: dimension={dim}, model=text-embedding-004")
            embed_text._dimension_logged = True
            
            # Check for dimension mismatch with existing vectors
            _check_dimension_mismatch(dim)
        
        return all_embeddings
        
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise RuntimeError(f"Vertex AI embedding generation failed: {e}") from e


def _check_dimension_mismatch(new_dim: int):
    """
    Check if existing vectors have different dimension and log warning.
    Does NOT modify or delete existing vectors.
    """
    try:
        from gdd_rag_backbone.config import DEFAULT_WORKING_DIR
        
        vdb_path = DEFAULT_WORKING_DIR / "vdb_chunks.json"
        if not vdb_path.exists():
            return
        
        data = json.loads(vdb_path.read_text(encoding="utf-8"))
        vectors = data.get("data", [])
        
        if not vectors:
            return
        
        # Check first vector's dimension
        first_vector = None
        for entry in vectors:
            vector = entry.get("vector") or entry.get("embedding")
            if vector:
                first_vector = vector
                break
        
        if first_vector:
            existing_dim = len(first_vector)
            if existing_dim != new_dim:
                logger.warning(
                    f"Embedding dimension mismatch detected: "
                    f"existing vectors have {existing_dim} dimensions, "
                    f"new embeddings have {new_dim} dimensions. "
                    f"Existing vectors will NOT be modified. "
                    f"To use new embeddings, re-index your documents."
                )
    except Exception as e:
        # Fail silently - dimension check is informational only
        logger.debug(f"Could not check dimension mismatch: {e}")

