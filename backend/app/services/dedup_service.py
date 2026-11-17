"""Duplicate detection for generated MCQ questions.

Questions are compared on a normalised form (lower-case, punctuation removed,
whitespace collapsed). Two questions are duplicates when the normalised texts
are identical or when their ``difflib`` similarity ratio reaches the threshold.
"""

from __future__ import annotations

import difflib
import hashlib
import re

DEFAULT_THRESHOLD = 0.85

_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Return a canonical form of ``text``: lower-case, no punctuation, single spaces."""
    lowered = (text or "").lower()
    stripped = _NON_WORD_RE.sub("", lowered)
    return _WS_RE.sub(" ", stripped).strip()


def question_hash(text: str) -> str:
    """Return the SHA-256 hex digest of the normalised question text."""
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def _similar(norm_a: str, norm_b: str, threshold: float) -> bool:
    """True when two already-normalised strings match exactly or are near-identical."""
    if norm_a == norm_b:
        return True
    matcher = difflib.SequenceMatcher(None, norm_a, norm_b)
    # quick_ratio() is an upper bound of ratio(); skip the expensive call when it cannot reach the threshold.
    if matcher.quick_ratio() < threshold:
        return False
    return matcher.ratio() >= threshold


def _is_duplicate_normalised(norm_candidate: str, norm_priors: list[str], threshold: float) -> bool:
    """True when ``norm_candidate`` duplicates any of the normalised ``norm_priors``."""
    for norm_prior in norm_priors:
        if _similar(norm_candidate, norm_prior, threshold):
            return True
    return False


def is_duplicate(candidate: str, prior_texts: list[str], threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Return True when ``candidate`` duplicates any text in ``prior_texts``.

    A duplicate is an exact normalised match or a ``difflib.SequenceMatcher``
    ratio greater than or equal to ``threshold`` (default 0.85).
    """
    norm_candidate = normalise(candidate)
    norm_priors = [normalise(prior) for prior in prior_texts if prior]
    return _is_duplicate_normalised(norm_candidate, norm_priors, threshold)


def filter_duplicates(
    candidates: list[dict],
    prior_texts: list[str],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[dict]:
    """Drop candidates that duplicate ``prior_texts`` or an earlier candidate.

    Each candidate is a dict with a ``"question"`` key. Candidates with an
    empty question are dropped as well. Order of the survivors is preserved.
    """
    norm_priors = [normalise(prior) for prior in prior_texts if prior]
    accepted: list[dict] = []
    accepted_norms: list[str] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        norm_candidate = normalise(str(candidate.get("question") or ""))
        if not norm_candidate:
            continue
        if _is_duplicate_normalised(norm_candidate, norm_priors, threshold):
            continue
        if _is_duplicate_normalised(norm_candidate, accepted_norms, threshold):
            continue
        accepted.append(candidate)
        accepted_norms.append(norm_candidate)

    return accepted
