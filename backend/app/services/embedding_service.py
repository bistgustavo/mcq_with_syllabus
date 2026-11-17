"""
Embedding service — wraps sentence-transformers ``all-MiniLM-L6-v2``.

The model is loaded lazily on first use (once per process) so the API starts
instantly and tests never download it.

Public API
----------
- ``embed(text) -> list[float]``             — single string → 384-dim vector
- ``embed_batch(texts) -> list[list[float]]`` — list of strings → list of vectors
- ``VECTOR_SIZE``                            — 384 for all-MiniLM-L6-v2
"""

from __future__ import annotations

import logging
import threading
from typing import Sequence

from app.config import settings

logger = logging.getLogger(__name__)

# all-MiniLM-L6-v2 produces 384-dim vectors. Kept as a constant so the vector
# store can be configured without loading the model.
VECTOR_SIZE: int = 384

_model = None
_lock = threading.Lock()


def get_model():
    """Load (once) and return the sentence-transformers model."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading sentence-transformers model '%s' …", settings.EMBEDDING_MODEL)
                model = SentenceTransformer(settings.EMBEDDING_MODEL)
                dim = model.get_sentence_embedding_dimension()
                if dim != VECTOR_SIZE:
                    raise RuntimeError(
                        f"Embedding model '{settings.EMBEDDING_MODEL}' has dimension {dim}, "
                        f"expected {VECTOR_SIZE}"
                    )
                _model = model
                logger.info("Embedding model loaded (dim=%d)", dim)
    return _model


def embed(text: str) -> list[float]:
    """Encode a single string into a dense vector."""
    return get_model().encode(text, show_progress_bar=False, normalize_embeddings=True).tolist()


def embed_batch(texts: Sequence[str], batch_size: int = 64) -> list[list[float]]:
    """Encode a batch of strings into dense vectors (one per input)."""
    if not texts:
        return []
    vectors = get_model().encode(
        list(texts), batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True
    )
    return vectors.tolist()
