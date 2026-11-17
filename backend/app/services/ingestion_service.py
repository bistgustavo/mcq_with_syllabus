"""
Ingestion service — PDF text extraction and chunking.

Accepts an uploaded PDF file path, uses pdfplumber to extract text page by page,
then chunks the text into ~500-token pieces with ~50-token overlap.  Returns a
flat list of ``{text, page_number}`` dicts ready for embedding.

Token estimation uses a simple heuristic: 1 token ≈ 0.75 words.  This avoids
pulling in a tokenizer dependency just for chunking and is accurate enough for
the ~500-token target the PROJECT SPEC calls for.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

import pdfplumber

logger = logging.getLogger(__name__)

# ── Chunking parameters (from PROJECT SPEC) ─────────────────────────────────
CHUNK_SIZE_TOKENS: int = 500
OVERLAP_TOKENS: int = 50

# Rough conversion factor: average English word ≈ 1.33 tokens
_WORDS_PER_TOKEN: float = 0.75
CHUNK_SIZE_WORDS: int = int(CHUNK_SIZE_TOKENS * _WORDS_PER_TOKEN)
OVERLAP_WORDS: int = int(OVERLAP_TOKENS * _WORDS_PER_TOKEN)


class TextChunk(TypedDict):
    """Shape returned to callers (and ultimately stored in Qdrant payloads)."""

    text: str
    page_number: int


# ── Public API ───────────────────────────────────────────────────────────────


def extract_text_from_pdf(file_path: str | Path) -> list[dict[str, str | int]]:
    """Extract raw text from *file_path* page-by-page.

    Returns a list of ``{"text": ..., "page_number": ...}`` where
    ``page_number`` is 1-indexed to match how humans refer to PDF pages.
    """

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found at {file_path}")

    pages: list[dict[str, str | int]] = []

    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            text: str | None = page.extract_text()
            if text and text.strip():
                pages.append({"text": text.strip(), "page_number": page_num})

    logger.info("Extracted text from %d / %d pages in %s", len(pages), total_pages, file_path.name)
    return pages


def count_pages(file_path: str | Path) -> int:
    """Return the number of pages in a PDF (0 if it cannot be opened)."""
    try:
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001
        return 0


def chunk_text(
    pages: list[dict[str, str | int]],
    chunk_size_words: int = CHUNK_SIZE_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> list[TextChunk]:
    """Split page-extracted texts into overlapping chunks.

    Each chunk is roughly *chunk_size_words* words long with *overlap_words*
    overlap so that sentences split across the boundary aren't lost.

    The ``page_number`` attached to each chunk is the page from which the
    **majority** of that chunk's words originate.
    """

    chunks: list[TextChunk] = []

    for page_data in pages:
        text: str = str(page_data["text"])
        page_number: int = int(page_data["page_number"])
        words: list[str] = text.split()

        if not words:
            continue

        step = max(chunk_size_words - overlap_words, 1)
        start = 0
        while start < len(words):
            end = start + chunk_size_words
            chunk_text_str = " ".join(words[start:end]).strip()
            if chunk_text_str:
                chunks.append(TextChunk(text=chunk_text_str, page_number=page_number))
            if end >= len(words):
                break  # the last window already reached the end of the page
            # Advance by (chunk_size - overlap) so consecutive chunks overlap.
            start += step

    logger.info("Produced %d chunks from %d pages", len(chunks), len(pages))
    return chunks


def extract_and_chunk(file_path: str | Path) -> list[TextChunk]:
    """Convenience wrapper: extract PDF text *and* chunk it in one call.

    This is the function the ingestion worker should call.
    """

    pages = extract_text_from_pdf(file_path)
    return chunk_text(pages)
