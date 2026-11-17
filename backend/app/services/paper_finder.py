"""Find past exam papers online, list them, and turn their MCQs into questions.

Connectors
* PSC (Lok Sewa Aayog) — the official question-bank API behind psc.gov.np
  (``/front/questionbank/``), filtered by designation (e.g. कम्प्युटर अधिकृत).
* NRB — the official "नमूना प्रश्नपत्र" archive on nrb.org.np (posts → PDF links).
* Web — metasearch for paper PDFs and pages that post scanned papers as images.

Every paper found becomes a ``PastPaper`` row straight away (so it appears in
the admin list), then is processed: download → text (OCR for scans) → MCQ
extraction → filed under the course's topics. Subjective-only papers are kept
and marked ``no_mcq``.

Database sessions are never kept in a transaction across slow network/AI
calls (a long-open transaction blocks schema changes and other writers).
"""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import settings
from app.models import Course, PastPaper
from app.models.past_paper import PAPER_DONE, PAPER_FAILED, PAPER_FOUND, PAPER_NO_MCQ, PAPER_PROCESSING
from app.services.past_paper_service import (
    _download,
    extract_mcqs,
    unit_names,
    extract_text,
    page_paper_assets,
    store_questions,
    windows,
)
from app.services.web_search_service import USER_AGENT, _ddg_search, _fetch_page_text

logger = logging.getLogger(__name__)

PSC_API = "https://psc.gov.np/front/questionbank/"
NRB_ARCHIVE = "https://www.nrb.org.np/category/model-questions/"
HEADERS = {"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest"}
SKIP_HOSTS = ("scribd.com", "studocu.com", "coursehero.com", "facebook.com", "youtube.com", "pinterest.")
MAX_OCR_PAGES = 80
_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")
_YEAR = re.compile(r"\b(20[5-9]\d)\b")
_OPTION = re.compile(r"(?:^|\s)\(?(?:[a-dA-D]|[क-घ])[\).]\s")
# Option labels as OCR really produces them: "(a)", "a)", "(9)"/"(0)" for (a)/(b), "(ख)", ...
_OPTION_OCR = re.compile(r"(?:^|\s)\(\s*[a-dA-D0-9क-घ]\s*\)|(?:^|\s)[a-dA-Dक-घ][\).]\s")
_QUESTION_NO = re.compile(r"(?m)^\s*(?:Q\.?\s*)?\d{1,3}\s*[.)]\s+\S")


@dataclass
class Candidate:
    title: str
    source: str
    file_url: str
    page_url: str | None = None
    year: str | None = None
    assets: list[str] = field(default_factory=list)


def _year(*texts: str | None) -> str | None:
    for t in texts:
        m = _YEAR.search((t or "").translate(_DEVANAGARI))
        if m:
            return m.group(1)
    return None


# --------------------------------------------------------------------------- search profile
def profile(course: Course) -> dict:
    """What to look for, derived from the course (NRB vs Lok Sewa, IT vs general)."""
    text = f"{course.name} {course.exam_name or ''}".lower()
    nrb = "rastra" in text or "nrb" in text
    loksewa = "lok sewa" in text or "loksewa" in text or "public service" in text
    it = any(k in text for k in ("information technology", "(it)", " it ", "computer"))
    prof: dict = {"psc": [], "nrb": [], "queries": []}
    if loksewa or ("computer officer" in text and not nrb):
        # Computer Officer papers, plus the same-level Section Officer papers (shared general paper).
        prof["psc"] = ["कम्प्युटर अधिकृत", "शाखा अधिकृत", "सूचना प्रविधि"]
        prof["queries"] += [
            "Lok Sewa computer officer old question paper pdf",
            "loksewa computer officer model question objective",
            "कम्प्युटर अधिकृत पुरानो प्रश्नपत्र",
        ]
    if nrb:
        prof["nrb"] = ["सहायक निर्देशक", "विभिन्न पद", "सूचना प्रविधि", "Information Technology", "Assistant Director"]
        prof["queries"] += [
            "NRB assistant director IT old question paper",
            "Nepal Rastra Bank assistant director information technology question paper pdf",
        ]
    if not prof["queries"]:
        prof["queries"] = [f"{course.name} old question paper pdf", f"{course.exam_name or course.name} model question"]
    if it and not prof["psc"] and not nrb:
        prof["psc"] = ["कम्प्युटर", "सूचना प्रविधि"]
    return prof


# --------------------------------------------------------------------------- connectors
def find_psc(keys: list[str]) -> list[Candidate]:
    """Papers from the PSC question bank whose designation matches ``keys``."""
    out: list[Candidate] = []
    page = 1
    while page <= 20:
        try:
            r = httpx.get(PSC_API, params={"page": page, "per_page": 100}, headers=HEADERS, timeout=30)
            data = r.json()["data"]["questionbanks"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("PSC question bank unavailable: %s", exc)
            break
        for qb in data.get("data") or []:
            designation = (qb.get("designation") or {}).get("title") or ""
            if not any(k in designation for k in keys):
                continue
            fy = qb.get("fiscalyear") or {}
            year = fy.get("start_from")
            group = (qb.get("group") or {}).get("name") or ""
            for f in qb.get("files") or []:
                if not f.get("location"):
                    continue
                name = re.sub(r"\.pdf$", "", f.get("name") or "paper", flags=re.I)
                out.append(Candidate(
                    title=f"PSC · {designation}{f' ({group})' if group else ''} · {year or ''} · {name}".replace(" ·  ·", " ·"),
                    source="psc", file_url=f["location"], page_url="https://psc.gov.np/category/question-bank", year=year,
                ))
        if page >= int(data.get("last_page") or 1):
            break
        page += 1
    return out


def find_nrb(keys: list[str], max_pages: int = 4) -> list[Candidate]:
    """Papers in NRB's official model/old question archive whose post title matches ``keys``."""
    out: list[Candidate] = []
    for n in range(1, max_pages + 1):
        url = NRB_ARCHIVE if n == 1 else f"{NRB_ARCHIVE}page/{n}/"
        try:
            page = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True).text
        except Exception as exc:  # noqa: BLE001
            logger.warning("NRB archive page %s unavailable: %s", n, exc)
            break
        posts = re.findall(r'<a[^>]+href="(https://www\.nrb\.org\.np/hrm/[^"]+)"[^>]*>(.*?)</a>', page, re.S)
        if not posts:
            break
        for post_url, raw_title in dict(posts).items():
            title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            if not any(k.lower() in title.lower() for k in keys):
                continue
            try:
                post = httpx.get(post_url, headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True).text
            except Exception:  # noqa: BLE001
                continue
            for pdf, link_text in re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', post, re.S):
                label = html.unescape(re.sub(r"<[^>]+>", "", link_text)).strip() or urllib.parse.unquote(pdf.rsplit("/", 1)[-1])
                out.append(Candidate(title=f"NRB · {title} · {label}"[:480], source="nrb", file_url=pdf,
                                     page_url=post_url, year=_year(title, label, pdf)))
    return out


_PAPER_LINK = re.compile(r"model question|old question|question paper|past paper|objective|mcq|प्रश्नपत्र|प्रश्न", re.I)


def _paper_page(url: str, title: str) -> Candidate | None:
    """A candidate if the page shows scanned papers or lists MCQs as text."""
    _, assets = page_paper_assets(url)
    if assets or len(_OPTION.findall(_fetch_page_text(url))) >= 8:
        return Candidate(title=f"Web · {title}"[:480], source="web", file_url=url, page_url=url,
                         year=_year(title, url), assets=assets)
    return None


def _child_paper_links(url: str, limit: int = 6) -> list[tuple[str, str]]:
    """Links on a listing/category page (same site) whose text looks like a question paper."""
    try:
        page = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True).text
    except Exception:  # noqa: BLE001
        return []
    host = urllib.parse.urlparse(url).netloc
    out: list[tuple[str, str]] = []
    for href, text in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', page, re.S):
        label = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
        link = urllib.parse.urljoin(url, href)
        if (urllib.parse.urlparse(link).netloc == host and link.rstrip("/") != url.rstrip("/")
                and not re.search(r"/(category|tag|page|author)/", link)
                and 12 <= len(label) <= 160 and _PAPER_LINK.search(label) and link not in dict(out)):
            out.append((link, label))
        if len(out) >= limit:
            break
    return out


def find_web(queries: list[str], max_pages: int = 10) -> list[Candidate]:
    """PDFs and pages with scanned papers found by web search."""
    out: list[Candidate] = []
    seen: set[str] = set()
    pages = 0
    for query in queries:
        for result in _ddg_search(query, 8):
            url = str(result.get("href") or "")
            title = str(result.get("title") or url)
            if not url.startswith("http") or url in seen or any(h in url for h in SKIP_HOSTS):
                continue
            seen.add(url)
            if url.lower().split("?")[0].endswith(".pdf"):
                out.append(Candidate(title=f"Web · {title}"[:480], source="web", file_url=url, page_url=url, year=_year(title, url)))
                continue
            if pages >= max_pages:
                continue
            pages += 1
            # A paper page either shows scans (images/PDFs) or lists the questions as text.
            found = _paper_page(url, title)
            if found:
                out.append(found)
                continue
            # A listing/category page: follow its links to the individual papers.
            for child, label in _child_paper_links(url):
                if child in seen:
                    continue
                seen.add(child)
                if child.lower().split("?")[0].endswith(".pdf"):
                    out.append(Candidate(title=f"Web · {label}"[:480], source="web", file_url=child, page_url=url, year=_year(label, child)))
                    continue
                found = _paper_page(child, label)
                if found:
                    out.append(found)
    return out


def discover(course: Course) -> list[Candidate]:
    prof = profile(course)
    found: list[Candidate] = []
    if prof["psc"]:
        found += find_psc(prof["psc"])
    if prof["nrb"]:
        found += find_nrb(prof["nrb"])
    found += find_web(prof["queries"])
    unique: dict[str, Candidate] = {}
    for c in found:
        unique.setdefault(c.file_url, c)
    return list(unique.values())


def save_candidates(db, course_id: int, candidates: list[Candidate]) -> int:
    """Insert new papers (status 'found'); existing ones are left as they are."""
    existing = set(db.scalars(select(PastPaper.file_url).where(PastPaper.course_id == course_id)).all())
    added = 0
    for c in candidates:
        if c.file_url[:767] in existing:
            continue
        db.add(PastPaper(course_id=course_id, title=c.title[:500], source=c.source, year=c.year,
                         page_url=(c.page_url or "")[:1000] or None, file_url=c.file_url[:767],
                         assets=c.assets or None, status=PAPER_FOUND))
        existing.add(c.file_url[:767])
        added += 1
    db.commit()
    return added


# --------------------------------------------------------------------------- processing
def _paper_dir(course_id: int) -> Path:
    folder = Path(settings.UPLOAD_DIR).resolve() / f"course-{course_id}" / "past-papers"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def looks_like_mcq(text: str) -> bool:
    """Heuristic, tolerant of OCR noise: option labels and numbered questions."""
    options = len(_OPTION_OCR.findall(text))
    questions = len(_QUESTION_NO.findall(text))
    return options >= 6 or (options >= 3 and questions >= 1)


def mcq_windows(text: str) -> list[str]:
    """Only the parts of a paper that look like MCQs (saves AI calls on subjective papers)."""
    return [w for w in windows(text) if looks_like_mcq(w)]


def process_paper(db_factory, paper_id: int) -> dict:
    """Download, read and extract one paper. Uses short sessions around slow steps."""
    db = db_factory()
    try:
        paper = db.get(PastPaper, paper_id)
        if paper is None:
            return {}
        paper.status, paper.error = PAPER_PROCESSING, None
        db.commit()
        course = db.get(Course, paper.course_id)
        exam = course.exam_name or course.name
        units = unit_names(db, paper.course_id)
        info = dict(file_url=paper.file_url, assets=list(paper.assets or []), stored=paper.stored_path,
                    title=paper.title, course_id=paper.course_id, source=paper.source, page_url=paper.page_url)
        db.rollback()  # end the read transaction before slow work
    finally:
        db.close()

    try:
        texts: list[str] = []
        ocr = False
        pages = 0
        folder = _paper_dir(info["course_id"])
        files: list[Path] = []
        if info["stored"]:
            files.append(Path(info["stored"]))
        elif info["source"] == "web" and not info["file_url"].lower().split("?")[0].endswith(".pdf"):
            # Web page: its own text (questions are often typed out) plus any scanned pages.
            page_text = _fetch_page_text(info["file_url"])
            if page_text:
                texts.append(page_text)
            for url in info["assets"]:
                dest = folder / f"{uuid.uuid4().hex}{Path(url.split('?')[0]).suffix.lower() or '.jpg'}"
                if _download(url, dest):
                    files.append(dest)
        elif info["assets"]:
            for n, url in enumerate(info["assets"]):
                dest = folder / f"{uuid.uuid4().hex}{Path(url.split('?')[0]).suffix.lower() or '.jpg'}"
                if _download(url, dest):
                    files.append(dest)
        else:
            dest = folder / f"{uuid.uuid4().hex}{Path(info['file_url'].split('?')[0]).suffix.lower() or '.pdf'}"
            if not _download(info["file_url"], dest):
                raise RuntimeError("Could not download the paper")
            files.append(dest)
        for path in files:
            text, used_ocr = extract_text(path, max_pages=MAX_OCR_PAGES)
            texts.append(text)
            ocr = ocr or used_ocr
            pages += max(1, text.count("\f") + 1) if path.suffix.lower() == ".pdf" else 1
        text = "\n".join(texts)
        relevant = mcq_windows(text)
        questions = []
        for piece in relevant:
            questions += extract_mcqs(piece, exam, units)

        db = db_factory()
        try:
            course = db.get(Course, info["course_id"])
            result = store_questions(db, course, questions, source="past_paper", reference=info["title"],
                                     min_score=0.32 if info["source"] == "web" else 0.25)
            paper = db.get(PastPaper, paper_id)
            paper.stored_path = str(files[0]) if files else None
            paper.ocr, paper.pages = ocr, pages
            paper.mcq_found, paper.mcq_added = result["found"], result["added"]
            paper.status = PAPER_DONE if result["found"] else PAPER_NO_MCQ
            paper.error = None if result["found"] else (
                "No multiple-choice questions found (subjective paper)" if len(text) > 300 else "No readable text"
            )
            db.commit()
            return {"id": paper_id, "status": paper.status, **result}
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Processing past paper %s failed: %s", paper_id, exc)
        db = db_factory()
        try:
            paper = db.get(PastPaper, paper_id)
            if paper is not None:
                paper.status, paper.error = PAPER_FAILED, str(exc)[:1000]
                db.commit()
        finally:
            db.close()
        return {"id": paper_id, "status": PAPER_FAILED, "error": str(exc)}
