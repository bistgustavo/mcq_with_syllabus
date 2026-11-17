"""Vector retrieval of syllabus context chunks for a topic.

All public functions are defensive: Qdrant or embedding failures are logged
and reported as "no chunks" so callers can degrade (e.g. to web search).
"""

from __future__ import annotations

import logging
import random

from app.config import settings
from app.services.embedding_service import embed
from app.vector_db import COLLECTION_NAME, get_client, topic_filter

logger = logging.getLogger(__name__)


def topic_chunk_count(topic_id: int, chapter_id: int | None = None) -> int:
    """Number of stored chunks for a topic (0 when unknown/unreachable)."""
    try:
        client = get_client()
        if not client.collection_exists(COLLECTION_NAME):
            return 0
        result = client.count(
            collection_name=COLLECTION_NAME, count_filter=topic_filter(topic_id, chapter_id), exact=True
        )
        return int(result.count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not count chunks for topic %s: %s", topic_id, exc)
        return 0


def _point_to_dict(payload: dict | None, score: float | None) -> dict | None:
    payload = payload or {}
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    raw_page = payload.get("page_number")
    try:
        page_number = int(raw_page) if raw_page is not None else None
    except (TypeError, ValueError):
        page_number = None
    source_type = payload.get("source_type")
    if not isinstance(source_type, str) or not source_type:
        source_type = "upload"
    try:
        score_value = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_value = 0.0
    return {"text": text.strip(), "page_number": page_number, "source_type": source_type, "score": score_value}


def retrieve_context(topic_id: int, query: str, top_k: int | None = None, chapter_id: int | None = None) -> list[dict]:
    """Retrieve relevant chunks of a topic for ``query``.

    ``top_k * 2`` candidates are fetched and a random sample of ``top_k`` is
    returned (ordered by score) so successive generations see varied context.
    Uploaded notes are preferred: web-search chunks are only used when the
    topic has no uploaded chunks among the candidates.
    """
    k = top_k if top_k is not None and top_k > 0 else settings.RETRIEVAL_TOP_K
    query_text = (query or "").strip()
    if not query_text:
        return []

    try:
        client = get_client()
        if not client.collection_exists(COLLECTION_NAME):
            return []
        vector = embed(query_text)
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            query_filter=topic_filter(topic_id, chapter_id),
            limit=k * 2,
            with_payload=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Retrieval failed for topic %s: %s", topic_id, exc)
        return []

    hits = [
        item
        for point in (getattr(response, "points", None) or [])
        if (item := _point_to_dict(getattr(point, "payload", None), getattr(point, "score", None)))
    ]
    uploads = [h for h in hits if h["source_type"] == "upload"]
    if uploads:
        hits = uploads
    if len(hits) > k:
        hits = random.sample(hits, k)
    hits.sort(key=lambda item: item["score"], reverse=True)
    logger.info("Retrieved %d context chunk(s) for topic %s", len(hits), topic_id)
    return hits
