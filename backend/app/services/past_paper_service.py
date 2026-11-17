"""Past papers and old questions → MCQs in the question bank.

* ``extract_text`` reads PDFs (text layer, or OCR with Tesseract for scans) and images.
* ``extract_mcqs`` asks the LLM to pull out every multiple-choice question from the
  text, keeping the official answer when the paper gives one and otherwise
  determining it, with a short explanation.
* ``assign_topics`` files each question under the best-matching topic of the course
  (embedding similarity), so practice and mock tests can use it.
* ``collect_online`` searches the web for old questions of the exam and extracts them.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chapter, Course, GeneratedQuestion, Topic
from app.services.dedup_service import question_hash
from app.services.embedding_service import embed_batch
from app.services.generation_service import CLOUD_PROVIDERS, GenerationError, generate, parse_questions

logger = logging.getLogger(__name__)

OCR_LANGS = "eng+nep"
WINDOW_CHARS = 6000
WINDOW_OVERLAP = 600
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

EXTRACT_PROMPT = """You are digitising a past examination paper for "{exam}".
Extract EVERY multiple-choice question that appears in the TEXT below. The text may come from OCR of a scan.

OCR NOTES: option labels are often misread, e.g. "(9)" or "(o)" for "(a)", "(0)" or "(6)" for "(b)", "(e)" for "(c)",
"(4)" for "(d)"; digits/letters get swapped ("INF" = "1NF", "0" = "O"). Options appear in a, b, c, d order.

RULES:
1. Keep the question and the four options as written, but remove option labels from the option text and fix
   obvious OCR errors (e.g. "INF" -> "1NF", "0 RSA" -> "RSA").
2. If the text states the answer (answer key, "Ans:", bold/marked option), use it as "correct_index".
   Otherwise solve the question yourself and double-check the answer against your knowledge.
3. "explanation": 1-2 sentences explaining why the answer is correct, as a standalone fact.
4. "difficulty": "easy", "medium" or "hard".
5. "unit": the number of the SYLLABUS UNIT below that the question belongs to (0 if none fits).
6. Skip questions that are incomplete, need a figure or diagram, or have fewer/more than 4 options.
7. Do not invent questions that are not in the text. If there are none, return {{"questions": []}}.
8. Output ONLY JSON of this shape:
{{"questions": [{{"question": "...", "options": ["...", "...", "...", "..."], "correct_index": 0, "explanation": "...", "difficulty": "medium", "unit": 1}}]}}

SYLLABUS UNITS:
{units}

TEXT:
{text}
"""


# --------------------------------------------------------------------------- text
def _ocr_image(path: Path) -> str:
    out = subprocess.run(["tesseract", str(path), "-", "-l", OCR_LANGS, "--psm", "6"],
                         capture_output=True, text=True, timeout=180)
    return out.stdout


def extract_text(path: Path, max_pages: int | None = None) -> tuple[str, bool]:
    """Return (text, used_ocr). Scanned PDFs (no text layer) are rasterised and OCR'd."""
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return _ocr_image(path), True
    if suffix != ".pdf":
        return path.read_text(encoding="utf-8", errors="ignore"), False

    import pdfplumber

    with pdfplumber.open(path) as pdf:
        pages = [(page.extract_text() or "") for page in pdf.pages[:max_pages]]
    text = "\f".join(pages)
    if len(text.strip()) >= 100 * max(1, len(pages)) * 0.5:
        # Text layer exists. OCR only the pages whose text is legacy-font gibberish.
        bad = [n for n, page_text in enumerate(pages, start=1) if looks_garbled(page_text, min_tokens=25)]
        if not bad or not shutil.which("pdftoppm") or not shutil.which("tesseract"):
            return text, False
        with tempfile.TemporaryDirectory() as tmp:
            for n in bad:
                subprocess.run(["pdftoppm", "-r", "200", "-f", str(n), "-l", str(n), "-png", str(path), f"{tmp}/p{n}"],
                               check=True, timeout=300)
                images = sorted(Path(tmp).glob(f"p{n}*.png"))
                if images:
                    pages[n - 1] = _ocr_image(images[0])
        return "\f".join(pages), True

    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        raise RuntimeError("This PDF is scanned and OCR tools (pdftoppm, tesseract) are not installed")
    with tempfile.TemporaryDirectory() as tmp:
        limit = ["-l", str(max_pages)] if max_pages else []
        subprocess.run(["pdftoppm", "-r", "200", *limit, "-png", str(path), f"{tmp}/page"], check=True, timeout=900)
        images = sorted(Path(tmp).glob("page*.png"))
        return "\f".join(_ocr_image(img) for img in images), True


_CLEAN_WORD = re.compile(r"^[A-Za-z][a-z]+[.,;:?!)]?$|^[\u0900-\u097F]+[।,?]?$|^\d+[.)]?$")


def looks_garbled(text: str, min_tokens: int = 40) -> bool:
    """True when a PDF text layer is legacy-font gibberish (e.g. Preeti) rather than real words.

    Nepali papers typed in legacy fonts extract as strings like "tqm qlTrq ter"; such
    PDFs must be OCR'd instead. Real English or Unicode Nepali text is mostly clean words.
    """
    tokens = text.split()
    if len(tokens) < min_tokens:
        return False
    clean = sum(1 for t in tokens if _CLEAN_WORD.match(t))
    odd = sum(1 for t in tokens if re.search(r"[{}|*\\~^]|[a-z][A-Z][a-z]", t))
    return clean / len(tokens) < 0.55 or odd / len(tokens) > 0.12


def windows(text: str, size: int = WINDOW_CHARS, overlap: int = WINDOW_OVERLAP) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        out.append(text[start : start + size])
        start += size - overlap
    return out


# --------------------------------------------------------------------------- LLM extraction
def extract_mcqs(text: str, exam: str, units: list[str] | None = None) -> list[dict]:
    """All MCQs found in ``text`` (deduplicated within the document).

    ``units`` (chapter names) let the model say which syllabus unit each question
    belongs to; it is returned as ``unit_index`` (0-based) when valid.
    """
    unit_text = "\n".join(f"{n}. {u}" for n, u in enumerate(units or [], start=1)) or "(not provided)"
    import json as _json
    found: list[dict] = []
    seen: set[str] = set()
    pieces = windows(text)
    failures = 0
    for piece in pieces:
        try:
            # Cloud models only: the AI often has to work out the answer itself, and the
            # small local model gets too many answers wrong for a question bank.
            raw = generate(EXTRACT_PROMPT.format(exam=exam, text=piece, units=unit_text), CLOUD_PROVIDERS)["raw"]
        except GenerationError as exc:
            failures += 1
            logger.warning("Extraction call failed: %s", exc)
            continue
        units_by_question = {}
        try:  # parse_questions drops unknown keys, so read "unit" from the raw JSON
            data = _json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            for item in data.get("questions", []):
                if isinstance(item, dict) and isinstance(item.get("unit"), int):
                    units_by_question[question_hash(str(item.get("question", "")))] = item["unit"]
        except Exception:  # noqa: BLE001
            pass
        for q in parse_questions(raw):
            unit = units_by_question.get(question_hash(q["question"]))
            if units and isinstance(unit, int) and 1 <= unit <= len(units):
                q["unit_index"] = unit - 1
            key = question_hash(q["question"])
            if key not in seen:
                seen.add(key)
                found.append(q)
    if pieces and failures == len(pieces):
        # Never report "no MCQs" when the AI was simply unavailable: let the caller mark it failed.
        raise GenerationError(f"MCQ extraction failed for all {failures} part(s); the AI models were unavailable")
    return found


# --------------------------------------------------------------------------- storing
def unit_names(db: Session, course_id: int, paper: str | None = None) -> list[str]:
    """Chapter names in the same order ``course_topics`` groups them (for the extraction prompt)."""
    stmt = select(Chapter).where(Chapter.course_id == course_id)
    if paper:
        stmt = stmt.where(Chapter.paper == paper)
    return [f"{c.name}{f' ({c.paper.split(chr(58))[0]})' if c.paper else ''}"
            for c in db.scalars(stmt.order_by(Chapter.order, Chapter.id)).all()
            if db.scalar(select(Topic.id).where(Topic.chapter_id == c.id).limit(1))]


def course_topics(db: Session, course_id: int, paper: str | None = None) -> list[Topic]:
    stmt = select(Topic).join(Chapter, Chapter.id == Topic.chapter_id).where(Chapter.course_id == course_id)
    if paper:
        stmt = stmt.where(Chapter.paper == paper)
    return list(db.scalars(stmt.order_by(Chapter.order, Topic.id)).all())


def assign_topics(topics: list[Topic], questions: list[dict]) -> list[tuple[Topic, float]]:
    """Best-matching topic (and its cosine score) for each question."""
    chapter_names = {t.chapter_id: t.chapter.name for t in topics}
    topic_vecs = np.array(embed_batch([f"{chapter_names[t.chapter_id]}: {t.name}. {t.description or ''}" for t in topics]))
    q_vecs = np.array(embed_batch([f"{q['question']} {q['options'][q['correct_index']]}" for q in questions]))
    scores = q_vecs @ topic_vecs.T
    best = scores.argmax(axis=1)
    return [(topics[int(i)], float(scores[n, int(i)])) for n, i in enumerate(best)]


def store_questions(
    db: Session, course: Course, questions: list[dict], source: str, reference: str,
    paper: str | None = None, min_score: float = 0.15,
) -> dict:
    """File questions under topics of ``course``. Off-syllabus ones (low similarity) are skipped."""
    topics = course_topics(db, course.id, paper)
    if not topics or not questions:
        return {"found": len(questions), "added": 0, "off_syllabus": 0, "duplicates": 0}
    added = off = dup = 0
    chapter_order: list[int] = []
    for t in topics:
        if t.chapter_id not in chapter_order:
            chapter_order.append(t.chapter_id)
    assigned = []
    for q in questions:
        unit = q.get("unit_index")
        pool = [t for t in topics if unit is not None and unit < len(chapter_order) and t.chapter_id == chapter_order[unit]]
        topic, score = assign_topics(pool or topics, [q])[0]
        if pool:
            score = max(score, 1.0)  # the model placed it in a syllabus unit: on-syllabus by definition
        assigned.append((topic, score))
    for q, (topic, score) in zip(questions, assigned):
        if score < min_score:
            off += 1
            continue
        digest = question_hash(q["question"])
        if db.scalar(select(GeneratedQuestion.id).join(Topic, Topic.id == GeneratedQuestion.topic_id)
                     .join(Chapter, Chapter.id == Topic.chapter_id)
                     .where(Chapter.course_id == course.id, GeneratedQuestion.question_hash == digest)):
            dup += 1
            continue
        db.add(GeneratedQuestion(
            topic_id=topic.id, question_text=q["question"], options=q["options"], correct_index=q["correct_index"],
            explanation=q.get("explanation") or "", source=source, difficulty=q.get("difficulty") or "medium",
            question_hash=digest, reference=reference[:500],
        ))
        added += 1
    db.commit()
    return {"found": len(questions), "added": added, "off_syllabus": off, "duplicates": dup}


def import_past_paper(db: Session, course: Course, path: Path, label: str, paper: str | None = None) -> dict:
    text, used_ocr = extract_text(path)
    if len(text.strip()) < 50:
        raise RuntimeError("No readable text found in the file")
    questions = extract_mcqs(text, course.exam_name or course.name, unit_names(db, course.id, paper))
    result = store_questions(db, course, questions, source="past_paper", reference=label, paper=paper)
    return {**result, "ocr": used_ocr, "characters": len(text)}


# --------------------------------------------------------------------------- online collection
MAX_ASSETS_PER_PAGE = 8
MAX_ASSET_BYTES = 12 * 1024 * 1024
_SKIP_IMG = re.compile(r"logo|icon|avatar|cropped|banner|(?<![a-z])ads?[-_/]|emoji|gravatar|placeholder|spinner", re.I)
_PAPER_HINT = re.compile(r"question|paper|old|exam|model|प्रश्न|set", re.I)


def _download(url: str, dest: Path) -> bool:
    import httpx

    from app.services.web_search_service import USER_AGENT

    try:
        with httpx.stream("GET", url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            size = 0
            with dest.open("wb") as out:
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_ASSET_BYTES:
                        return False
                    out.write(chunk)
        return size > 2000
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not download %s: %s", url, exc)
        return False


def page_paper_assets(url: str) -> tuple[str, list[str]]:
    """(page HTML text, URLs of question-paper images/PDFs on the page)."""
    from urllib.parse import urljoin

    import httpx

    from app.services.web_search_service import USER_AGENT

    try:
        html = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}).text
    except Exception:  # noqa: BLE001
        return "", []
    assets: list[str] = []
    for src in re.findall(r'href="([^"]+\.pdf)(?:\?[^"]*)?"', html, re.I):
        assets.append(urljoin(url, src))
    for src in re.findall(r'<img[^>]+?(?:data-src|data-lazy-src|src)="([^"]+\.(?:jpe?g|png|webp))"', html, re.I):
        if not _SKIP_IMG.search(src) and _PAPER_HINT.search(src):
            assets.append(urljoin(url, src))
    unique = list(dict.fromkeys(assets))
    return html, unique[:MAX_ASSETS_PER_PAGE]


def ocr_assets(urls: list[str]) -> str:
    """Download question-paper images/PDFs and return their text (OCR when scanned)."""
    texts = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, asset in enumerate(urls):
            suffix = Path(asset.split("?")[0]).suffix.lower() or ".jpg"
            dest = Path(tmp) / f"asset{n}{suffix}"
            if not _download(asset, dest):
                continue
            try:
                text, _ = extract_text(dest)
                texts.append(text)
            except Exception as exc:  # noqa: BLE001
                logger.info("Could not read %s: %s", asset, exc)
    return "\n".join(texts)
def online_queries(course: Course) -> list[str]:
    exam = course.exam_name or course.name
    name = course.name
    queries = [
        f"{name} old questions MCQ with answers",
        f"{name} objective questions previous year",
        f"{exam} model questions MCQ",
    ]
    lowered = f"{name} {exam}".lower()
    if "rastra" in lowered or "nrb" in lowered:
        queries += ["NRB IT officer old question objective", "Nepal Rastra Bank computer MCQ old questions"]
    if "lok sewa" in lowered or "loksewa" in lowered:
        queries += ["Lok Sewa computer officer old questions MCQ", "loksewa computer objective questions with answers"]
    return queries


def collect_online(db: Session, course: Course, max_pages: int = 12, progress=None) -> dict:
    """Search the web for old questions of this exam and import the MCQs found."""
    from app.services.web_search_service import _ddg_search, _fetch_page_text

    seen: set[str] = set()
    pages = []
    for query in online_queries(course):
        for result in _ddg_search(query, 6):
            url = str(result.get("href") or "")
            if url and url not in seen and url.startswith(("http://", "https://")):
                seen.add(url)
                pages.append((url, result.get("title") or url))
        if len(pages) >= max_pages:
            break

    totals = {"pages": 0, "found": 0, "added": 0, "off_syllabus": 0, "duplicates": 0, "sources": []}
    for n, (url, title) in enumerate(pages[:max_pages]):
        if progress:
            progress(n, len(pages[:max_pages]), title)
        text = _fetch_page_text(url)
        # Old papers are usually posted as scanned images or PDFs: OCR them too.
        _, assets = page_paper_assets(url)
        if assets:
            if progress:
                progress(n, len(pages[:max_pages]), f"{title} — reading {len(assets)} scanned page(s)")
            text = f"{text}\n{ocr_assets(assets)}"
        if len(text) < 300:
            continue
        questions = extract_mcqs(text[:40_000], course.exam_name or course.name)
        # Stricter topic match for web material: other posts' papers (e.g. Economics) must not leak in.
        result = store_questions(db, course, questions, source="online", reference=url, min_score=0.32)
        totals["pages"] += 1
        for key in ("found", "added", "off_syllabus", "duplicates"):
            totals[key] += result[key]
        if result["added"]:
            totals["sources"].append({"url": url, "title": str(title)[:120], "added": result["added"]})
    return totals
