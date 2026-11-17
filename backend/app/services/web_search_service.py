"""Web-search fallback for topics without uploaded notes.

Searches DuckDuckGo for the topic, downloads the result pages, strips the HTML
with a regex-based cleaner (no bs4 is installed) and returns short text
snippets. The snippets can then be embedded and stored in Qdrant exactly like
PDF chunks (``source_type="web_search"``) so later generations reuse them.

``search_topic_context`` never raises: on total failure it returns ``[]``.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re

import httpx

from app.config import settings

from app.services.embedding_service import embed_batch
from app.vector_db import upsert_chunks

logger = logging.getLogger(__name__)

MAX_SNIPPET_CHARS = 4000  # text kept per page (split into ~1200-char chunks when stored)
CHUNK_CHARS = 1200
MIN_TEXT_CHARS = 120  # below this the fetched page is considered useless -> use DDG body
MIN_FRAGMENT_CHARS = 40  # paragraphs shorter than this are usually menu items / labels
MAX_HTML_CHARS = 400_000  # cap on raw HTML processed per page
FETCH_TIMEOUT_SECONDS = 8.0
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_NOISE_RE = re.compile(
    r"<(script|style|noscript|head|nav|footer|aside|iframe|svg|form)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_FRAGMENT_RE = re.compile(
    r"<(p|li|h[1-6]|td|blockquote|dd)\b[^>]*>(.*?)</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_BLOCK_BREAK_RE = re.compile(
    r"</?(?:p|div|br|li|h[1-6]|tr|section|article|table|ul|ol)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_tags(fragment: str) -> str:
    """Remove HTML tags from ``fragment``, unescape entities and collapse whitespace."""
    text = _BLOCK_BREAK_RE.sub(" ", fragment)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def html_to_text(raw_html: str) -> str:
    """Convert an HTML document to plain text using regular expressions only.

    Scripts, styles, navigation and similar noise are removed first. The text
    of paragraph-like elements is preferred; if that yields too little, the
    whole document body is stripped of tags instead.
    """
    raw = (raw_html or "")[:MAX_HTML_CHARS]
    raw = _COMMENT_RE.sub(" ", raw)
    raw = _NOISE_RE.sub(" ", raw)

    fragments: list[str] = []
    for match in _FRAGMENT_RE.finditer(raw):
        fragment = _strip_tags(match.group(2))
        if len(fragment) >= MIN_FRAGMENT_CHARS:
            fragments.append(fragment)

    text = " ".join(fragments)
    if len(text) < MIN_TEXT_CHARS:
        text = _strip_tags(raw)
    return text


def _truncate_words(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` characters, preferably at a word boundary."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space >= int(limit * 0.7):
        cut = cut[:space]
    return cut.strip()


def _fetch_page_text(url: str) -> str:
    """Download ``url`` and return its cleaned text; returns ``""`` on any failure."""
    try:
        response = httpx.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if content_type and "html" not in content_type and "text/plain" not in content_type:
            logger.debug("Skipping non-HTML content (%s) at %s", content_type, url)
            return ""
        if "text/plain" in content_type:
            return _WS_RE.sub(" ", response.text).strip()
        return html_to_text(response.text)
    except Exception as exc:  # noqa: BLE001 - network/HTTP/decoding errors all mean "no page text"
        logger.debug("Could not fetch %s: %s", url, exc)
        return ""


def _ddg_search(query: str, max_results: int) -> list[dict]:
    """Metasearch via ``ddgs``, trying each configured backend until one answers.

    Free search endpoints rate-limit aggressively, so several backends are
    tried in order (``SEARCH_BACKENDS``, default "bing,yandex,duckduckgo").
    Returns ``[]`` when every backend fails.
    """
    try:
        from ddgs import DDGS
    except ImportError:  # pragma: no cover
        logger.error("The 'ddgs' package is not installed")
        return []
    for backend in [b.strip() for b in settings.SEARCH_BACKENDS.split(",") if b.strip()]:
        try:
            results = DDGS(timeout=10).text(query, max_results=max_results, backend=backend)
            rows = [r for r in (results or []) if isinstance(r, dict) and r.get("href")]
            if rows:
                return rows
        except Exception as exc:  # noqa: BLE001 - try the next backend
            logger.info("Search backend %s failed for %r: %s", backend, query, str(exc)[:120])
    logger.warning("All search backends failed for %r", query)
    return []


WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "QuizForge/2.0 (exam-preparation platform)"}


def _wikipedia(query: str, limit: int = 2) -> list[dict]:
    """Reliable fallback: plain-text extracts of the best-matching Wikipedia articles."""
    try:
        found = httpx.get(
            WIKI_API,
            params={"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"},
            headers=WIKI_HEADERS,
            timeout=FETCH_TIMEOUT_SECONDS,
        ).json()
        titles = [hit["title"] for hit in found.get("query", {}).get("search", [])]
        if not titles:
            return []
        pages = httpx.get(
            WIKI_API,
            params={"action": "query", "prop": "extracts", "explaintext": 1, "exlimit": len(titles),
                    "titles": "|".join(titles), "format": "json", "redirects": 1},
            headers=WIKI_HEADERS,
            timeout=FETCH_TIMEOUT_SECONDS,
        ).json()
        out = []
        for page in pages.get("query", {}).get("pages", {}).values():
            text = _WS_RE.sub(" ", page.get("extract") or "").strip()
            if len(text) >= MIN_TEXT_CHARS:
                title = page.get("title", "")
                out.append({"url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}", "title": title, "body": text})
        return out
    except Exception as exc:  # noqa: BLE001
        logger.info("Wikipedia lookup failed for %r: %s", query, exc)
        return []


def build_queries(
    topic_name: str,
    chapter_name: str | None,
    course_name: str | None,
    detail: str | None = None,
    exam_name: str | None = None,
) -> list[str]:
    """Build the search queries for a topic (deduplicated, non-empty).

    Uses the topic, its chapter, the admin-written syllabus detail and the
    exam name, so research stays inside the official syllabus.
    """
    topic = _WS_RE.sub(" ", topic_name or "").strip()
    chapter = (chapter_name or "").strip()
    detail_text = _WS_RE.sub(" ", detail or "").strip()[:120]
    combined = " ".join(p for p in (topic, chapter) if p)
    explained = f"{topic} {detail_text}".strip() if detail_text else f"{topic} explained".strip()
    exam = (exam_name or course_name or "").strip()
    exam_q = f"{topic} {exam} MCQ notes".strip() if exam else ""

    queries: list[str] = []
    for query in (combined, explained, exam_q):
        if query and query not in queries:
            queries.append(query)
    return queries


def search_topic_context(
    topic_name: str,
    chapter_name: str | None,
    course_name: str | None,
    max_results: int = 5,
    detail: str | None = None,
    exam_name: str | None = None,
) -> list[dict]:
    """Search the web for material about a topic and return cleaned text snippets.

    Two queries are issued (``"<topic> <chapter> <course>"`` and
    ``"<topic> explained"``). Every result URL is fetched with an 8 second
    timeout and cleaned; when the page cannot be fetched or is too short the
    DuckDuckGo result body is used instead.

    Returns up to ``max_results`` dicts with keys ``text`` (<= ~1500 chars),
    ``url`` and ``title``. Never raises; returns ``[]`` on total failure.
    """
    snippets: list[dict] = []
    if max_results <= 0:
        return snippets

    try:
        queries = build_queries(topic_name, chapter_name, course_name, detail=detail, exam_name=exam_name)
        if not queries:
            logger.warning("Web search skipped: empty topic name")
            return snippets

        candidates: list[dict] = []
        seen_urls: set[str] = set()
        for query in queries:
            for result in _ddg_search(query, max_results):
                url = str(result.get("href") or "").strip()
                if not url or url in seen_urls or not url.lower().startswith(("http://", "https://")):
                    continue
                seen_urls.add(url)
                candidates.append(
                    {
                        "url": url,
                        "title": _WS_RE.sub(" ", str(result.get("title") or "")).strip(),
                        "body": _WS_RE.sub(" ", str(result.get("body") or "")).strip(),
                    }
                )

        if len(candidates) < max_results:
            # Search engines rate-limit; Wikipedia's API is a dependable fallback.
            for page in _wikipedia(queries[0]) + (_wikipedia(topic_name) if queries[0] != topic_name else []):
                if page["url"] not in seen_urls:
                    seen_urls.add(page["url"])
                    candidates.append({**page, "prefetched": True})

        logger.info("Web search for %r returned %d candidate page(s)", topic_name, len(candidates))

        for candidate in candidates:
            if len(snippets) >= max_results:
                break
            text = candidate["body"] if candidate.get("prefetched") else _fetch_page_text(candidate["url"])
            if len(text) < MIN_TEXT_CHARS:
                text = candidate["body"]
            text = _truncate_words(text, MAX_SNIPPET_CHARS)
            if not text:
                continue
            snippets.append({"text": text, "url": candidate["url"], "title": candidate["title"]})
    except Exception as exc:  # noqa: BLE001 - this function must never raise
        logger.warning("Web search failed for topic %r: %s", topic_name, exc)

    logger.info("Web search for %r produced %d snippet(s)", topic_name, len(snippets))
    return snippets


def persist_web_context(topic_id: int, chapter_id: int, snippets: list[dict]) -> int:
    """Embed web snippets and store them in Qdrant as ``web_search`` chunks.

    Returns the number of chunks upserted (0 when there was nothing to store).
    Errors from the embedding model or Qdrant propagate to the caller.
    """
    stored = 0
    for snippet in snippets:
        text = str(snippet.get("text") or "").strip()
        if not text:
            continue
        pieces = split_text(text, CHUNK_CHARS)
        vectors = embed_batch(pieces)
        # One deterministic key per (topic, url): re-running a search refreshes
        # the same points instead of piling up duplicates.
        url_hash = hashlib.sha1(str(snippet.get("url") or text).encode("utf-8")).hexdigest()
        stored += upsert_chunks(
            vectors=vectors,
            texts=pieces,
            topic_id=topic_id,
            chapter_id=chapter_id,
            source_type="web_search",
            page_numbers=[0] * len(pieces),
            document_key=f"web-{topic_id}-{url_hash}",
        )
    logger.info("Persisted %s web-search chunk(s) for topic %s", stored, topic_id)
    return stored


def split_text(text: str, size: int) -> list[str]:
    """Split ``text`` into ~``size``-char pieces on sentence/word boundaries."""
    text = text.strip()
    pieces: list[str] = []
    while len(text) > size:
        cut = text.rfind(". ", 0, size)
        if cut < size * 0.5:
            cut = text.rfind(" ", 0, size)
        cut = cut + 1 if cut > 0 else size
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        pieces.append(text)
    return pieces
