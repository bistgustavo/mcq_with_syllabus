"""
Qdrant wrapper — collection setup, idempotent upserts and filtered deletes.

The client is created lazily so importing this module never touches the
network. Point IDs are deterministic (UUID5 of document id + chunk index), so a
retried ingestion overwrites its own points instead of duplicating them.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.config import settings
from app.services.embedding_service import VECTOR_SIZE

logger = logging.getLogger(__name__)

COLLECTION_NAME: str = settings.QDRANT_COLLECTION
_POINT_NAMESPACE = uuid.UUID("6f1c7a3e-2d4b-4c1e-9a55-0b7e3f1d2c90")
_INDEXED_FIELDS = ("topic_id", "chapter_id", "document_id")

_client: QdrantClient | None = None
_client_lock = threading.Lock()
_collection_ready = False


def get_client() -> QdrantClient:
    """Return the process-wide Qdrant client (created on first use)."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from app.infra import qdrant_endpoint

                endpoint = qdrant_endpoint()
                _client = QdrantClient(url=endpoint.url, api_key=endpoint.api_key or None, timeout=30)
    return _client


class _LazyClient:
    """Proxy kept for backwards compatibility with ``from app.vector_db import qdrant_client``."""

    def __getattr__(self, name: str):
        return getattr(get_client(), name)


qdrant_client = _LazyClient()


def ensure_collection() -> None:
    """Create the collection and its payload indexes if they do not exist (idempotent)."""
    global _collection_ready
    if _collection_ready:
        return
    client = get_client()
    if not client.collection_exists(COLLECTION_NAME):
        logger.info("Creating Qdrant collection '%s' (size=%d, cosine)", COLLECTION_NAME, VECTOR_SIZE)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    for field, schema in [*((f, PayloadSchemaType.INTEGER) for f in _INDEXED_FIELDS), ("scope", PayloadSchemaType.KEYWORD)]:
        try:
            client.create_payload_index(collection_name=COLLECTION_NAME, field_name=field, field_schema=schema)
        except Exception as exc:  # noqa: BLE001 - index already exists is fine
            logger.debug("Payload index %s not created: %s", field, exc)
    _collection_ready = True


def point_id(document_key: str, index: int) -> str:
    """Deterministic point id for chunk ``index`` of a document."""
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{document_key}:{index}"))


def upsert_chunks(
    vectors: Sequence[list[float]],
    texts: Sequence[str],
    topic_id: int | None,
    chapter_id: int,
    source_type: str,
    page_numbers: Sequence[int],
    document_id: int | None = None,
    document_key: str | None = None,
) -> int:
    """``topic_id=None`` stores chapter-wide content (scope "chapter")."""
    """Batch-upsert embedded chunks. Returns the number of points written."""
    if not (len(vectors) == len(texts) == len(page_numbers)):
        raise ValueError(
            f"Length mismatch: vectors={len(vectors)}, texts={len(texts)}, page_numbers={len(page_numbers)}"
        )
    if not vectors:
        return 0

    ensure_collection()
    key = document_key or (f"doc-{document_id}" if document_id is not None else uuid.uuid4().hex)
    points = [
        PointStruct(
            id=point_id(key, i),
            vector=vector,
            payload={
                "topic_id": topic_id,
                "chapter_id": chapter_id,
                "scope": "topic" if topic_id is not None else "chapter",
                "document_id": document_id,
                "text": text,
                "source_type": source_type,
                "page_number": page_number,
            },
        )
        for i, (vector, text, page_number) in enumerate(zip(vectors, texts, page_numbers))
    ]

    client = get_client()
    batch_size = 128
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=COLLECTION_NAME, points=points[i : i + batch_size], wait=True)

    logger.info("Upserted %d points into '%s' (topic_id=%s)", len(points), COLLECTION_NAME, topic_id)
    return len(points)


def _match(field: str, value: int) -> Filter:
    return Filter(must=[FieldCondition(key=field, match=MatchValue(value=int(value)))])


def topic_filter(topic_id: int, chapter_id: int | None = None) -> Filter:
    """Points of the topic itself, plus chapter-wide notes of its chapter."""
    if chapter_id is None:
        return _match("topic_id", topic_id)
    return Filter(
        should=[
            FieldCondition(key="topic_id", match=MatchValue(value=int(topic_id))),
            Filter(
                must=[
                    FieldCondition(key="chapter_id", match=MatchValue(value=int(chapter_id))),
                    FieldCondition(key="scope", match=MatchValue(value="chapter")),
                ]
            ),
        ]
    )


def delete_points(field: str, value: int) -> None:
    """Delete every point whose payload ``field`` equals ``value`` (no-op if the collection is missing)."""
    client = get_client()
    if not client.collection_exists(COLLECTION_NAME):
        return
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(filter=_match(field, value)),
        wait=True,
    )
