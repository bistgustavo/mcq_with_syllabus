"""LLM-backed MCQ generation with provider fallback and a Redis circuit breaker.

Provider order is Ollama (local ``mistral:7b``) -> Groq -> Gemini. A provider
is skipped when it is not configured or when it recently failed (a Redis key
``llm:cooldown:<provider>`` with a 5 minute TTL). Redis problems never break
generation: the circuit breaker silently degrades to "always try".

The prompt is kept lean (about 6000 characters) because the local model runs
on CPU; context chunks are trimmed proportionally to fit the budget.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable

import httpx

from app.config import settings
from app.redis_client import redis_client
from app.services.dedup_service import DEFAULT_THRESHOLD, _is_duplicate_normalised, normalise

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Raised when no LLM provider could produce a usable response."""


PROVIDER_ORDER: tuple[str, ...] = ("groq", "gemini", "ollama")  # default; settings.provider_order wins
MAX_ATTEMPTS = 2

MAX_PROMPT_CHARS = 6000  # soft budget for the whole prompt
PRIOR_SHARE = 0.3  # share of the variable budget reserved for prior questions
PRIOR_QUESTION_MAX_CHARS = 110  # each prior question is truncated to this length
MIN_CONTEXT_BUDGET = 1500  # the context always gets at least this many characters
MIN_CHUNK_CHARS = 150  # budget needed per chunk: limits how many chunks are included
MIN_PIECE_CHARS = 80  # floor for a trimmed chunk so it stays readable

VALID_DIFFICULTIES: tuple[str, ...] = ("easy", "medium", "hard")
MIXED = "mixed"  # one call, a spread of levels; each question carries its own "difficulty"

DIFFICULTY_GUIDANCE: dict[str, str] = {
    "easy": (
        "EASY - test direct recall of definitions, facts, names and key terms that are stated "
        "plainly in the context; distractors must be clearly distinguishable from the answer."
    ),
    "medium": (
        "MEDIUM - test understanding and application of the concepts in the context (why/how, "
        "cause-effect, simple scenarios); distractors must be plausible and related to the topic."
    ),
    "hard": (
        "HARD - test analysis, comparison, exceptions and multi-step reasoning over the context; "
        "distractors must be subtle so that only a careful reader picks the correct option."
    ),
    MIXED: (
        "MIXED - write roughly one third EASY (direct recall of facts and definitions), one third MEDIUM "
        "(understanding and application) and one third HARD (analysis, comparison, multi-step reasoning, subtle "
        'distractors). Label each question with "difficulty": "easy", "medium" or "hard".'
    ),
}

JSON_SHAPE = (
    '{"questions": [{"question": "...", "options": ["...", "...", "...", "..."], '
    '"correct_index": 0, "explanation": "...", "difficulty": "medium"}]}'
)

SYSTEM_INSTRUCTION = (
    "You are a strict examiner. You write multiple-choice questions only from the syllabus "
    "context supplied by the user and you reply with a single JSON object and nothing else."
)

_WS_RE = re.compile(r"\s+")
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)
_FENCE_RE = re.compile(r"```[A-Za-z0-9_-]*")
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_RETRY_IN_RE = re.compile(r"try again in ([\d.]+)\s*(ms|s|m)\b")
_OPTION_PREFIX_RE = re.compile(r"^\(?(?:[A-Da-d]|[1-4])[\)\.:]\s+")

_INDEX_KEYS: tuple[str, ...] = (
    "correct_index",
    "answer_index",
    "correct_option_index",
    "correct_option",
    "correct_answer",
    "answer",
    "correct",
)


# --------------------------------------------------------------------------- #
# Prompt building
# --------------------------------------------------------------------------- #
def normalise_difficulty(difficulty: str | None) -> str:
    """Map a difficulty string to ``easy``/``medium``/``hard``/``mixed`` (default medium)."""
    value = (difficulty or "").strip().lower()
    return value if value in VALID_DIFFICULTIES or value == MIXED else "medium"


def _clean_text(text: Any) -> str:
    """Collapse whitespace in ``text`` (converted to str) and strip it."""
    return _WS_RE.sub(" ", str(text if text is not None else "")).strip()


def _truncate(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` characters, preferably at a word boundary, adding '...'."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    cut = text[: max(limit - 3, 1)]
    space = cut.rfind(" ")
    if space >= int(len(cut) * 0.6):
        cut = cut[:space]
    return cut.rstrip() + "..."


def _fit_context(chunks: list[str], budget: int) -> list[str]:
    """Trim ``chunks`` proportionally so that the numbered context block fits in ``budget`` chars."""
    cleaned = [_clean_text(chunk) for chunk in chunks]
    cleaned = [chunk for chunk in cleaned if chunk]
    if not cleaned or budget <= 0:
        return []

    # Never include more chunks than can each keep a meaningful size.
    max_chunks = max(1, budget // MIN_CHUNK_CHARS)
    cleaned = cleaned[:max_chunks]

    overhead = sum(len(f"[{index}] ") + 1 for index in range(1, len(cleaned) + 1))
    text_budget = max(budget - overhead, 0)
    total = sum(len(chunk) for chunk in cleaned)
    if total <= text_budget:
        return cleaned

    ratio = text_budget / total if total else 0.0
    trimmed: list[str] = []
    for chunk in cleaned:
        # Proportional share, but never below a small readable floor (soft budget).
        allowed = max(int(len(chunk) * ratio), min(len(chunk), MIN_PIECE_CHARS))
        piece = _truncate(chunk, allowed)
        if piece:
            trimmed.append(piece)
    return trimmed


def _build_context_block(context_chunks: list[str], budget: int) -> str:
    """Render the numbered syllabus context section."""
    fitted = _fit_context(context_chunks, budget)
    if not fitted:
        return "(no context available)\n"
    return "".join(f"[{index}] {chunk}\n" for index, chunk in enumerate(fitted, start=1))


def _build_prior_block(prior_questions: list[str], budget: int) -> str:
    """Render the list of previously asked questions the model must not repeat."""
    cleaned: list[str] = []
    for question in prior_questions:
        text = _clean_text(question)
        if text:
            cleaned.append(_truncate(text, PRIOR_QUESTION_MAX_CHARS))
        if len(cleaned) >= settings.MAX_PRIOR_QUESTIONS:
            break

    if not cleaned:
        return "\nPREVIOUSLY ASKED QUESTIONS: none.\n"

    title = "\nPREVIOUSLY ASKED QUESTIONS (do not repeat or paraphrase any of these):\n"
    used = len(title)
    lines: list[str] = []
    for text in cleaned:
        line = f"- {text}\n"
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line)

    if not lines:
        return "\nPREVIOUSLY ASKED QUESTIONS: none.\n"
    return title + "".join(lines)


def build_prompt(
    topic_name: str,
    context_chunks: list[str],
    prior_questions: list[str],
    count: int,
    difficulty: str,
    exam_name: str | None = None,
    syllabus_scope: str | None = None,
) -> str:
    """Build the generation prompt for ``count`` MCQs on ``topic_name``.

    ``exam_name`` (e.g. "NRB Computer Officer") makes the questions follow
    that exam's paper style; ``syllabus_scope`` is the admin-written syllabus
    text for the topic, which bounds what may be asked.

    The prompt instructs the model to act as an examiner, to use only the
    numbered syllabus context, to avoid the listed prior questions and to
    output a single JSON object of the exact expected shape. Context chunks
    are trimmed proportionally so the whole prompt stays under roughly
    ``MAX_PROMPT_CHARS`` characters.
    """
    count = max(1, int(count))
    level = normalise_difficulty(difficulty)
    topic = _clean_text(topic_name) or "the given topic"

    exam = _clean_text(exam_name)
    scope = _truncate(_clean_text(syllabus_scope), 600)
    exam_line = (
        f'These questions are for candidates preparing for the "{exam}" examination; match the style, '
        "precision and level of that exam's objective (MCQ) paper.\n"
        if exam
        else ""
    )
    scope_line = f"OFFICIAL SYLLABUS FOR THIS TOPIC: {scope}\n" if scope else ""
    header = (
        f'You are a strict examiner writing multiple-choice questions (MCQs) on the topic "{topic}".\n'
        + exam_line
        + scope_line
        + "Write every question STRICTLY from the SYLLABUS CONTEXT below and within the official syllabus. "
        "Do not ask about anything the context does not cover.\n\n"
        f"TASK: write exactly {count} {level.upper()} MCQ(s).\n"
        f"DIFFICULTY GUIDANCE: {DIFFICULTY_GUIDANCE[level]}\n\n"
        "RULES:\n"
        "1. Every question has exactly 4 options and exactly one correct option.\n"
        '2. "correct_index" is the 0-based position (0, 1, 2 or 3) of the correct option; '
        "spread the correct answers over different positions.\n"
        '3. "explanation" is 1-2 sentences that teach why the answer is correct, written as a standalone fact '
        '(never mention "the context", "the passage", "the text" or "the syllabus").\n'
        "3b. Questions must also be standalone: never refer to the context or to the source material.\n"
        "4. Vary the sub-topics: cover different parts of the context and never ask twice about the same fact.\n"
        "5. Do NOT repeat or paraphrase any of the PREVIOUSLY ASKED QUESTIONS.\n"
        '6. Options must be distinct, similar in length, and never "all of the above" or "none of the above".\n'
        "7. Output ONLY a JSON object of this exact shape - no markdown, no comments, no text before or after:\n"
        f"{JSON_SHAPE}\n\n"
        "SYLLABUS CONTEXT:\n"
    )
    footer = f"\nNow write the {count} question(s) as a single JSON object:"

    remaining = max(MAX_PROMPT_CHARS - len(header) - len(footer), MIN_CONTEXT_BUDGET)
    prior_budget = int(remaining * PRIOR_SHARE)
    prior_block = _build_prior_block(prior_questions, prior_budget)
    context_budget = max(remaining - len(prior_block), MIN_CONTEXT_BUDGET)
    context_block = _build_context_block(context_chunks, context_budget)

    prompt = header + context_block + prior_block + footer
    logger.debug("Built prompt of %d characters for topic %r (%d MCQs, %s)", len(prompt), topic, count, level)
    return prompt


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #
def _strip_wrappers(raw: str) -> str:
    """Remove ``<think>`` blocks and markdown code fences from a raw model response."""
    text = _THINK_BLOCK_RE.sub("", raw)
    text = _THINK_TAG_RE.sub("", text)
    text = _FENCE_RE.sub("", text)
    return text.strip()


def _loads_lenient(candidate: str) -> Any | None:
    """``json.loads`` with a trailing-comma repair fallback; returns None when both fail."""
    for attempt in (candidate, _TRAILING_COMMA_RE.sub(r"\1", candidate)):
        try:
            return json.loads(attempt)
        except ValueError:
            continue
    return None


def _loads_between(text: str, open_char: str, close_char: str) -> Any | None:
    """Parse the outermost ``open_char ... close_char`` span of ``text`` as JSON."""
    start = text.find(open_char)
    end = text.rfind(close_char)
    if start == -1 or end <= start:
        return None
    return _loads_lenient(text[start : end + 1])


def _items_from_data(data: Any) -> list:
    """Extract the list of question-like items from parsed JSON data."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        questions = data.get("questions")
        if isinstance(questions, list):
            return [item for item in questions if isinstance(item, dict)]
        if "question" in data or "question_text" in data:
            return [data]
        for value in data.values():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                return list(value)
    return []


def _salvage_objects(text: str) -> list:
    """Last resort: pull out every complete JSON object that looks like a question.

    Handles responses truncated by a token limit, where the outer object is
    incomplete but several inner question objects are intact.
    """
    decoder = json.JSONDecoder()
    items: list = []
    pos = 0
    length = len(text)
    while pos < length:
        start = text.find("{", pos)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except ValueError:
            pos = start + 1
            continue
        if isinstance(obj, dict):
            if "question" in obj or "question_text" in obj:
                items.append(obj)
                pos = end
                continue
            nested = _items_from_data(obj)
            if nested:
                items.extend(nested)
                pos = end
                continue
        pos = start + 1
    return items


def _extract_items(text: str) -> list:
    """Locate and parse the question items inside cleaned model output."""
    items = _items_from_data(_loads_between(text, "{", "}"))
    if items:
        return items
    items = _items_from_data(_loads_between(text, "[", "]"))
    if items:
        return items
    return _salvage_objects(text)


def _coerce_index(value: Any, options: list[str]) -> int | None:
    """Convert a model supplied answer marker into an int 0-3 (or None if impossible)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 3 else None
    if isinstance(value, float):
        return _coerce_index(int(value), options) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return _coerce_index(int(text), options)
        letter = text.strip("()").rstrip(".:").strip().upper()
        if len(letter) == 1 and letter in "ABCD":
            return "ABCD".index(letter)
        lowered = text.lower()
        for index, option in enumerate(options):
            if option.strip().lower() == lowered:
                return index
    return None


def _clean_options(raw_options: Any) -> list[str] | None:
    """Validate and normalise the options of one item; returns None when invalid."""
    if isinstance(raw_options, dict):
        raw_options = list(raw_options.values())
    if not isinstance(raw_options, list) or len(raw_options) != 4:
        return None

    options: list[str] = []
    for option in raw_options:
        if isinstance(option, bool):
            return None
        if isinstance(option, (int, float)):
            option = str(option)
        if not isinstance(option, str):
            return None
        cleaned = _clean_text(option)
        if not cleaned:
            return None
        options.append(cleaned)

    # Strip consistent "A) " / "1. " prefixes only when every option carries one.
    if all(_OPTION_PREFIX_RE.match(option) for option in options):
        stripped = [_OPTION_PREFIX_RE.sub("", option, count=1).strip() for option in options]
        if all(stripped):
            options = stripped
    return options


def _validate_item(item: Any) -> dict | None:
    """Validate one parsed question item and return it in canonical form (or None)."""
    if not isinstance(item, dict):
        return None

    question = item.get("question")
    if question is None:
        question = item.get("question_text")
    if not isinstance(question, str):
        return None
    question = _clean_text(question)
    if not question:
        return None

    options = _clean_options(item.get("options"))
    if options is None:
        return None

    correct_index: int | None = None
    for key in _INDEX_KEYS:
        if key in item:
            correct_index = _coerce_index(item.get(key), options)
            if correct_index is not None:
                break
    if correct_index is None:
        return None

    explanation = item.get("explanation", "")
    if explanation is None:
        explanation = ""
    if not isinstance(explanation, str):
        explanation = str(explanation)
    explanation = _clean_text(explanation)

    level = str(item.get("difficulty") or "").strip().lower()
    return {
        "question": question,
        "options": options,
        "correct_index": correct_index,
        "explanation": explanation,
        "difficulty": level if level in VALID_DIFFICULTIES else None,
    }


def parse_questions(raw: str) -> list[dict]:
    """Parse a raw model response into validated question dicts.

    Steps: strip ``<think>`` blocks and code fences, parse the outermost JSON
    object (falling back to the largest JSON array, then to salvaging complete
    inner objects), validate every item (non-empty question, exactly 4
    non-empty options, ``correct_index`` 0-3, explanation string) and drop
    duplicates within the batch by normalised question text.
    """
    if not isinstance(raw, str) or not raw.strip():
        return []

    text = _strip_wrappers(raw)
    items = _extract_items(text)

    valid: list[dict] = []
    seen: set[str] = set()
    for item in items:
        question = _validate_item(item)
        if question is None:
            continue
        key = normalise(question["question"])
        if not key or key in seen:
            continue
        seen.add(key)
        valid.append(question)

    logger.info("Parsed %d valid question(s) out of %d item(s)", len(valid), len(items))
    return valid


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
def _cooldown_key(provider: str) -> str:
    """Redis key used as the circuit breaker flag for ``provider``."""
    return f"llm:cooldown:{provider}"


import contextlib
import contextvars

# Background jobs may wait for a provider to come back instead of failing fast.
_PATIENCE: contextvars.ContextVar[float] = contextvars.ContextVar("llm_patience", default=0.0)


@contextlib.contextmanager
def patient(seconds: float = 600.0):
    """Within this block, ``generate`` waits (up to ``seconds`` per call) when every provider is cooling down."""
    token = _PATIENCE.set(seconds)
    try:
        yield
    finally:
        _PATIENCE.reset(token)


def _cooldown_left(provider: str) -> float:
    try:
        ttl = redis_client.ttl(_cooldown_key(provider))
        return float(ttl) if ttl and ttl > 0 else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def _in_cooldown(provider: str) -> bool:
    """True when ``provider`` failed recently; Redis errors count as "not in cooldown"."""
    try:
        return bool(redis_client.exists(_cooldown_key(provider)))
    except Exception as exc:  # noqa: BLE001 - Redis must never break generation
        logger.debug("Redis unavailable while checking cooldown for %s: %s", provider, exc)
        return False


def _rate_limit_seconds(exc: Exception) -> int | None:
    """Seconds to back off if ``exc`` is a rate-limit / quota error, else None."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    name = type(exc).__name__
    text = str(exc).lower()
    is_limit = (
        status == 429
        or name in ("RateLimitError", "ResourceExhausted", "TooManyRequests")
        or "rate limit" in text
        or "quota" in text
    )
    if not is_limit:
        return None
    # Per-minute limits mention TPM/RPM or "try again in N s"; they must not be mistaken for a
    # daily quota just because the message also links to a billing page.
    per_minute = any(w in text for w in ("per minute", "(tpm)", "(rpm)", "tokens per minute", "requests per minute"))
    daily = any(w in text for w in ("per day", "(tpd)", "(rpd)", "daily", "exceeded your current quota"))
    if daily and not per_minute:
        return settings.RATE_LIMIT_COOLDOWN_SECONDS
    # Per-minute limit: wait only as long as the provider asks (+ a small margin).
    wait = 0.0
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        wait = float(headers.get("retry-after", 0) or 0)
    except (TypeError, ValueError):
        wait = 0.0
    match = _RETRY_IN_RE.search(text)
    if match:
        value, unit = float(match.group(1)), match.group(2)
        wait = max(wait, value / 1000 if unit == "ms" else value * 60 if unit == "m" else value)
    return int(min(max(wait + 3, 15), settings.RATE_LIMIT_COOLDOWN_SECONDS))


def _set_cooldown(provider: str, seconds: int | None = None) -> None:
    """Skip ``provider`` for ``seconds`` (default PROVIDER_COOLDOWN_SECONDS); Redis errors are ignored."""
    try:
        redis_client.set(_cooldown_key(provider), "1", ex=int(seconds or settings.PROVIDER_COOLDOWN_SECONDS))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis unavailable while setting cooldown for %s: %s", provider, exc)


def _is_configured(provider: str) -> bool:
    """True when the settings needed for ``provider`` are present."""
    if provider == "ollama":
        return bool(settings.OLLAMA_BASE_URL and settings.OLLAMA_MODEL)
    if provider == "groq":
        return bool(settings.GROQ_API_KEY and settings.GROQ_MODEL)
    if provider == "gemini":
        return bool(settings.GEMINI_API_KEY and settings.GEMINI_MODEL)
    return False


def _call_ollama(prompt: str) -> tuple[str, str]:
    """Generate with the local Ollama server; returns ``(raw_text, model_name)``."""
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.8, "num_ctx": 4096},
    }
    response = httpx.post(
        url,
        json=payload,
        timeout=httpx.Timeout(float(settings.OLLAMA_TIMEOUT), connect=5.0),
    )
    response.raise_for_status()
    data = response.json()
    text = data.get("response") if isinstance(data, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise GenerationError("Ollama returned an empty response")
    return text, settings.OLLAMA_MODEL


def _call_groq(prompt: str) -> tuple[str, str]:
    """Generate with Groq; returns ``(raw_text, model_name)``.

    Groq rate-limits each model separately, so when the primary model hits its
    per-minute limit the fallback model is tried (each model has its own cooldown).
    """
    from groq import Groq  # imported lazily so the module loads even without the SDK

    client = Groq(api_key=settings.GROQ_API_KEY, timeout=float(settings.CLOUD_TIMEOUT), max_retries=0)
    models = [m for m in dict.fromkeys([settings.GROQ_MODEL, settings.GROQ_FALLBACK_MODEL]) if m]
    last_exc: Exception | None = None
    for model in models:
        if _in_cooldown(f"groq:{model}"):
            continue
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            limited = _rate_limit_seconds(exc)
            if limited is None:
                raise
            _set_cooldown(f"groq:{model}", limited)
            last_exc = exc
            continue
        text = completion.choices[0].message.content if completion.choices else None
        if not isinstance(text, str) or not text.strip():
            raise GenerationError("Groq returned an empty response")
        return text, model
    if last_exc is not None:
        raise last_exc
    raise GenerationError("All Groq models are cooling down after rate limits")


def _call_gemini(prompt: str) -> tuple[str, str]:
    """Generate with Google Gemini; returns ``(raw_text, model_name)``."""
    import google.generativeai as genai  # imported lazily so the module loads even without the SDK

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        settings.GEMINI_MODEL,
        generation_config={"response_mime_type": "application/json", "temperature": 0.8},
        system_instruction=SYSTEM_INSTRUCTION,
    )
    response = model.generate_content(prompt, request_options={"timeout": float(settings.CLOUD_TIMEOUT)})
    try:
        text = response.text
    except ValueError as exc:  # blocked / empty candidates
        raise GenerationError(f"Gemini returned no text: {exc}") from exc
    if not isinstance(text, str) or not text.strip():
        raise GenerationError("Gemini returned an empty response")
    return text, settings.GEMINI_MODEL


_PROVIDER_CALLS: dict[str, Callable[[str], tuple[str, str]]] = {
    "ollama": _call_ollama,
    "groq": _call_groq,
    "gemini": _call_gemini,
}


CLOUD_PROVIDERS: tuple[str, ...] = ("groq", "gemini")


def generate(prompt: str, providers: tuple[str, ...] | None = None) -> dict:
    """See ``_generate_once``. Inside ``patient()``, waits for cooled-down providers and retries."""
    deadline = time.monotonic() + _PATIENCE.get()
    while True:
        try:
            return _generate_once(prompt, providers)
        except GenerationError:
            candidates = [p for p in settings.provider_order if (providers is None or p in providers) and _is_configured(p)]
            waits = [_cooldown_left(p) for p in candidates]
            wait = min(waits) if waits else 0.0
            if not candidates or time.monotonic() + max(wait, 1.0) > deadline:
                raise
            logger.info("All LLM providers busy; waiting %.0fs for the first to come back", max(wait, 1.0))
            time.sleep(max(wait, 1.0) + 1.0)


def _generate_once(prompt: str, providers: tuple[str, ...] | None = None) -> dict:
    """Send ``prompt`` to the first healthy provider (ollama -> groq -> gemini).

    Returns ``{"raw": str, "source": provider, "model": model_name}``. A
    provider that is unconfigured or in cooldown is skipped; one that raises
    or times out is put in cooldown and the next one is tried. Raises
    ``GenerationError`` when every provider is unavailable or failed.
    """
    failures: list[str] = []
    for provider in settings.provider_order:
        if providers is not None and provider not in providers:
            continue
        if not _is_configured(provider):
            logger.info("LLM provider %s skipped: not configured", provider)
            continue
        if _in_cooldown(provider):
            logger.info("LLM provider %s skipped: in cooldown after a recent failure", provider)
            failures.append(f"{provider}: in cooldown")
            continue

        started = time.monotonic()
        try:
            raw, model = _PROVIDER_CALLS[provider](prompt)
        except Exception as exc:  # noqa: BLE001 - any provider error falls through to the next
            elapsed = time.monotonic() - started
            logger.warning(
                "LLM provider %s failed after %.1fs (%s: %s); trying the next provider",
                provider,
                elapsed,
                type(exc).__name__,
                exc,
            )
            limited = _rate_limit_seconds(exc)
            reason = "rate limited" if limited else f"{type(exc).__name__}: {exc}"
            failures.append(f"{provider}: {reason}"[:300])
            _set_cooldown(provider, limited)
            continue

        elapsed = time.monotonic() - started
        logger.info("LLM provider %s (%s) answered in %.1fs with %d chars", provider, model, elapsed, len(raw))
        return {"raw": raw, "source": provider, "model": model}

    detail = "; ".join(failures) if failures else "no LLM provider is configured"
    raise GenerationError(f"All LLM providers failed: {detail}")


# --------------------------------------------------------------------------- #
# High level API
# --------------------------------------------------------------------------- #
def generate_mcqs(
    topic_name: str,
    context_chunks: list[str],
    prior_questions: list[str],
    count: int = 10,
    difficulty: str = "medium",
    exam_name: str | None = None,
    syllabus_scope: str | None = None,
    providers: tuple[str, ...] | None = None,
) -> dict:
    """Generate up to ``count`` validated MCQs for a topic.

    Makes at most ``MAX_ATTEMPTS`` (2) provider calls: when the first attempt
    yields fewer valid questions than requested, a second call asks only for
    the missing number (listing the questions already obtained as "previously
    asked" so they are not repeated).

    Returns ``{"questions": [...], "source": str, "model": str, "attempts": int}``.
    Raises ``GenerationError`` when no provider answered or no valid question
    could be parsed at all.
    """
    count = max(1, int(count))
    level = normalise_difficulty(difficulty)

    accepted: list[dict] = []
    accepted_keys: set[str] = set()
    # Near-duplicates of earlier questions are rejected here (not only after
    # generation) so the follow-up attempt can make up for them.
    prior_norms = [n for n in (normalise(q) for q in prior_questions) if n]
    source = ""
    model = ""
    best_contribution = -1
    attempts = 0

    while attempts < MAX_ATTEMPTS and len(accepted) < count:
        missing = count - len(accepted)
        prior_for_prompt = list(prior_questions) + [question["question"] for question in accepted]
        prompt = build_prompt(
            topic_name, context_chunks, prior_for_prompt, missing, level,
            exam_name=exam_name, syllabus_scope=syllabus_scope,
        )
        attempts += 1

        try:
            result = generate(prompt, providers) if providers is not None else generate(prompt)
        except GenerationError as exc:
            if accepted:
                logger.warning("Attempt %d failed (%s); returning the %d question(s) already obtained", attempts, exc, len(accepted))
                break
            raise

        parsed = parse_questions(result["raw"])
        contribution = 0
        for question in parsed:
            key = normalise(question["question"])
            if not key or key in accepted_keys:
                continue
            if _is_duplicate_normalised(key, prior_norms, DEFAULT_THRESHOLD):
                continue
            accepted_keys.add(key)
            question["source"] = result["source"]
            question["model"] = result["model"]
            accepted.append(question)
            contribution += 1
            if len(accepted) >= count:
                break

        if contribution > best_contribution:
            best_contribution = contribution
            source = result["source"]
            model = result["model"]

        if len(accepted) < count:
            logger.info(
                "Attempt %d produced %d new question(s); %d/%d collected so far",
                attempts,
                contribution,
                len(accepted),
                count,
            )

    if not accepted:
        raise GenerationError("The language model returned no valid questions; please try again")

    logger.info(
        "Generated %d/%d question(s) for topic %r via %s (%s) in %d attempt(s)",
        len(accepted),
        count,
        topic_name,
        source,
        model,
        attempts,
    )
    return {"questions": accepted[:count], "source": source, "model": model, "attempts": attempts}
