"""Import the candidate's NRB / Lok Sewa study notes into the platform.

    venv/bin/python -m scripts.import_notes --notes-dir ~/Desktop/nrb

For every syllabus unit (chapter) this stores the unit's notes as chapter-wide
knowledge (Qdrant, scope "chapter"), so the AI writes its questions from the
notes instead of from the web.

By default the MCQs already written in the notes are NOT copied: the platform's
AI generates the question bank itself. Pass ``--with-mcqs`` to also import the
notes' curated MCQs (source "notes"), each assigned to the best-matching topic.

Sources:
* notes_source/*.html — one file per unit, with sections, model answers,
  "Question bank → A. Multiple-choice questions" and "Answer key: MCQs".
  For Computer Officer units shared with NRB, MCQs listed under ``drop_mcq`` in
  notes_source/make_co_edition.py (read statically, never executed) are skipped,
  matching the Computer Officer editions of the notes.
* computer operator/1. General Knowledge and Reasoning/Lok_Sewa_Paper_I_Master_Notes.pdf
  — Part I notes, "Practice MCQs — 1.N" sections and the 50-question model test.

Idempotent: re-running replaces the notes documents and skips MCQs already imported.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Chapter, Course, GeneratedQuestion, SyllabusDocument, Topic
from app.services.dedup_service import question_hash
from app.services.embedding_service import embed_batch
from app.services.web_search_service import split_text
from app.vector_db import delete_points, upsert_chunks
from app.workers.ingestion_worker import refresh_chapter_has_content

AD = "NRB Assistant Director (IT)"
CO = "Computer Officer (Lok Sewa Aayog)"

# (course, paper prefix or None, chapter name) -> notes files
AD_MAP = {
    ("Paper I", "Computer Architecture & Organization and Microprocessors"): ["p1_ch1_architecture.html"],
    ("Paper I", "Digital Logic Design"): ["p1_ch2_digital_logic.html"],
    ("Paper I", "Operating Systems"): ["p1_ch3_os.html"],
    ("Paper I", "Database Management System and Design"): ["p1_ch4_dbms.html"],
    ("Paper I", "Computer Networks"): ["p1_ch5_networks.html"],
    ("Paper I", "Distributed System"): ["p1_ch6_distributed.html"],
    ("Paper I", "Cryptography and Network Security"): ["p1_ch7_crypto_network_security.html"],
    ("Paper II", "Programming Language"): ["p2_ch1_programming.html"],
    ("Paper II", "Data Structure and Algorithms"): ["p2_ch2_dsa.html"],
    ("Paper II", "Discrete Mathematics"): ["p2_ch3_discrete_math.html"],
    ("Paper II", "Compiler Design"): ["p2_ch4_compiler.html"],
    ("Paper II", "System Analysis and Design"): ["p2_ch5_sad.html"],
    ("Paper II", "Software Engineering Principles"): ["p2_ch6_software_engineering.html"],
    ("Paper II", "MIS and Web Engineering"): ["p2_ch7_mis_web.html"],
    ("Paper II", "Computer Graphics"): ["p2_ch8_computer_graphics.html"],
    ("Paper III", "IT in Central Bank (NRB) and Nepalese Banking Sector"): ["p3_ch1_it_in_banking.html"],
    ("Paper III", "Relevant Acts, Policies and Guidelines"): ["p3_ch2_acts_policies.html"],
    ("Paper III", "Internet and Network Programming"): ["p3_ch3_network_programming.html"],
    ("Paper III", "Cyber Security and Ethics"): ["p3_ch4_cyber_security.html"],
    ("Paper III", "FinTech, RegTech and SupTech"): ["p3_ch5_fintech.html"],
    ("Paper III", "E-Commerce Technology"): ["p3_ch6_ecommerce.html"],
    ("Paper III", "E-Governance"): ["p3_ch7_egovernance.html"],
    ("Paper III", "Artificial Intelligence and Machine Learning"): ["p3_ch8_ai_ml.html"],
    ("Paper III", "Cloud Computing"): ["p3_ch9_cloud.html"],
    ("Paper III", "Development in Virtual Currency"): ["p3_ch10_virtual_currency.html"],
}
CO_MAP = {
    ("Part II", "Computer Fundamentals"): ["co_u01_computer_fundamentals.html"],
    ("Part II", "Data Structure and Algorithms"): ["p2_ch2_dsa.html"],
    ("Part II", "System Analysis and Design"): ["p2_ch5_sad.html"],
    ("Part II", "Operating Systems"): ["p1_ch3_os.html", "co_u04b_windows_linux_admin.html"],
    ("Part II", "Database Management System and Design"): ["p1_ch4_dbms.html"],
    ("Part II", "Programming Language"): ["p2_ch1_programming.html"],
    ("Part II", "Networking"): ["p1_ch5_networks.html", "co_u07b_network_admin.html"],
    ("Part II", "Computer Architecture and Organization"): ["co_u08_computer_architecture.html"],
    ("Part II", "Compiler Design"): ["p2_ch4_compiler.html"],
    ("Part II", "E-Commerce Technology"): ["p3_ch6_ecommerce.html"],
    ("Part II", "MIS and Web Engineering"): ["p2_ch7_mis_web.html"],
    ("Part II", "IT in Nepal"): ["co_u12_it_in_nepal.html"],
}
GK_CHAPTERS = {
    "1": "General Awareness and Contemporary Issues",
    "2.1": "Logical (Verbal) Reasoning",
    "2.2": "Numerical Reasoning",
    "2.3": "Spatial (Non-verbal) Reasoning",
}
REFERENCE = "Study notes"
GK_PDF = "computer operator/1. General Knowledge and Reasoning/Lok_Sewa_Paper_I_Master_Notes.pdf"


# --------------------------------------------------------------------------- parsing
@dataclass
class MCQ:
    question: str
    options: list[str]
    answer: int
    explanation: str = ""
    section: str | None = None  # e.g. "1.4" for GK practice sets


@dataclass
class Notes:
    title: str
    sections: list[tuple[str, str]] = field(default_factory=list)  # (heading, text)
    mcqs: list[MCQ] = field(default_factory=list)


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(fragment: str) -> str:
    fragment = re.sub(r"<(br|/p|/li|/tr|/h\d|/div)\b[^>]*>", " ", fragment, flags=re.I)
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


def parse_notes_html(path: Path, drop_mcq: set[int] | None = None) -> Notes:
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<(style|script)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.S)
    notes = Notes(title=clean(title_m.group(1)) if title_m else path.stem)

    # MCQs + key + explanations
    key = {int(n): "abcd".index(a) for n, a in re.findall(r'<div class="kc"><span>(\d+)</span>([a-d])</div>', raw)}
    expl = {int(n): clean(t) for n, t in re.findall(r'<li value="(\d+)"><b>[a-d]</b>\s*:?\s*(.*?)</li>', raw, re.S)}
    for n, q, opts in re.findall(
        r'<div class="mcq"><div class="q">\s*(\d+)\.\s*(.*?)</div><div class="opts">(.*?)</div></div>', raw, re.S
    ):
        n = int(n)
        options = [clean(o) for o in re.findall(r"<span>\s*[a-d]\)\s*(.*?)</span>", opts, re.S)]
        if len(options) != 4 or n not in key or (drop_mcq and n in drop_mcq):
            continue
        notes.mcqs.append(MCQ(question=clean(q), options=options, answer=key[n], explanation=expl.get(n, "")))

    # Knowledge text: everything before the question bank, split by h2/h3 headings.
    cut = re.search(r"<h2[^>]*>\s*[\d.]*\s*Question bank", raw)
    body = raw[: cut.start()] if cut else raw
    parts = re.split(r"(<h[23][^>]*>.*?</h[23]>)", body, flags=re.S)
    heading = notes.title
    for part in parts:
        if re.match(r"<h[23]", part):
            heading = clean(part)
            continue
        text = clean(part)
        if len(text) > 80:
            notes.sections.append((heading, text))
    return notes


def co_drop_lists(notes_dir: Path) -> dict[str, set[int]]:
    """Read UNITS[...] = dict(src=..., drop_mcq=[...]) from make_co_edition.py without executing it."""
    path = notes_dir / "notes_source" / "make_co_edition.py"
    if not path.exists():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, set[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "UNITS" for t in node.targets):
            for value in node.value.values:
                kw = {k.arg: k.value for k in getattr(value, "keywords", [])}
                if "src" in kw:
                    src = ast.literal_eval(kw["src"])
                    out[src] = set(ast.literal_eval(kw["drop_mcq"])) if "drop_mcq" in kw else set()
    return out


_OPT_LINE = re.compile(r"\(([a-d])\)\s*(.+?)(?=\s{2,}\([a-d]\)|\s*$)")


def parse_gk_pdf(pdf: Path) -> tuple[dict[str, str], list[MCQ]]:
    """Section texts by syllabus number, and all MCQs (practice sets + model test)."""
    plain = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    layout = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout

    # ---- sections (skip the contents page: start after the first "SECTION 1 ·" heading)
    start = plain.find("SECTION 1 ·")
    body = plain[start:] if start >= 0 else plain
    end = body.find("Appendix A")
    body = body[:end] if end > 0 else body
    sections: dict[str, str] = {}
    pieces = re.split(r"[\n\f](?=(1\.\d{1,2}|2\.[123]) [A-Z])", body)
    current = None
    for piece in pieces:
        m = re.match(r"(1\.\d{1,2}|2\.[123]) [A-Z]", piece)
        if m:
            current = m.group(1)
        if current and piece.strip() and not re.fullmatch(r"1\.\d{1,2}|2\.[123]", piece.strip()):
            sections[current] = sections.get(current, "") + "\n" + piece
    sections = {k: _WS.sub(" ", v).strip() for k, v in sections.items()}

    # ---- MCQs from the layout text
    mcqs: list[MCQ] = []
    lines = layout.splitlines()
    section = None
    model_test = False
    i = 0
    model: list[tuple[int, str, list[str]]] = []
    while i < len(lines):
        line = lines[i]
        sec = re.match(r"\s*Practice MCQs\s*[—-]\s*([\d.]+)", line)
        if sec:
            section = sec.group(1)
        if "Appendix B" in line and "Model Test" in line:
            model_test, section = True, None
        if line.strip().startswith("Answer Key") and model_test:
            break
        q = re.match(r"\s*(\d{1,2})\.\s+(\S.*)$", line)
        if q and (section or model_test):
            text = q.group(2).strip()
            j = i + 1
            while j < len(lines) and lines[j].strip() and not re.match(r"\s*\(a\)", lines[j]):
                text += " " + lines[j].strip()
                j += 1
            opts: dict[str, str] = {}
            while j < len(lines) and re.match(r"\s*\([a-d]\)", lines[j]):
                for letter, value in _OPT_LINE.findall(lines[j].strip()):
                    opts[letter] = _WS.sub(" ", value).strip()
                j += 1
            answer_m = re.match(r"\s*Answer:\s*\(([a-d])\)\s*(.*)$", lines[j]) if j < len(lines) else None
            if len(opts) == 4:
                options = [opts[k] for k in "abcd"]
                if answer_m and section:
                    mcqs.append(MCQ(_WS.sub(" ", text), options, "abcd".index(answer_m.group(1)),
                                    answer_m.group(2).strip(), section=section))
                elif model_test:
                    model.append((int(q.group(1)), _WS.sub(" ", text), options))
            i = j
            continue
        i += 1

    # model-test key: "1  b  reason   26  b  reason"
    key_start = layout.find("Answer Key", layout.find("Appendix B"))
    key: dict[int, tuple[int, str]] = {}
    for n, a, reason in re.findall(r"(?m)(?:^|\s{2,})(\d{1,2})\s+([a-d])\s+(.*?)(?=\s{3,}\d{1,2}\s+[a-d]\s|$)", layout[key_start:]):
        key.setdefault(int(n), ("abcd".index(a), reason.strip()))
    for n, text, options in model:
        if n in key:
            mcqs.append(MCQ(text, options, key[n][0], key[n][1], section="model-A" if n <= 25 else "model-B"))
    return sections, mcqs


# --------------------------------------------------------------------------- storing
def find_chapter(db, course: Course, paper_prefix: str | None, name: str) -> Chapter:
    for c in db.scalars(select(Chapter).where(Chapter.course_id == course.id)).all():
        if c.name == name and (paper_prefix is None or (c.paper or "").startswith(paper_prefix)):
            return c
    raise LookupError(f"{course.name}: chapter {paper_prefix} / {name!r} not found — run scripts.seed_nrb first")


def store_knowledge(db, chapter: Chapter, label: str, sections: list[tuple[str, str]]) -> int:
    """Replace the chapter-wide notes document ``label`` with fresh chunks."""
    doc = db.scalar(
        select(SyllabusDocument).where(SyllabusDocument.chapter_id == chapter.id, SyllabusDocument.filename == label)
    )
    if doc is None:
        doc = SyllabusDocument(chapter_id=chapter.id, topic_id=None, filename=label, source_type="upload", status="ready")
        db.add(doc)
        db.flush()
    else:
        delete_points("document_id", doc.id)

    texts: list[str] = []
    for heading, text in sections:
        for piece in split_text(text, 1100):
            texts.append(f"{chapter.name} › {heading}: {piece}")
    if not texts:
        return 0
    vectors = embed_batch(texts)
    stored = upsert_chunks(
        vectors=vectors, texts=texts, topic_id=None, chapter_id=chapter.id, source_type="upload",
        page_numbers=[0] * len(texts), document_id=doc.id, document_key=f"notes-{doc.id}",
    )
    doc.chunk_count, doc.status, doc.error = stored, "ready", None
    doc.file_size = sum(len(t) for t in texts)
    return stored


def assign_topics(topics: list[Topic], mcqs: list[MCQ]) -> list[Topic]:
    """Best-matching topic for each MCQ (cosine similarity of embeddings)."""
    topic_vecs = np.array(embed_batch([f"{t.name}. {t.description or ''}" for t in topics]))
    q_vecs = np.array(embed_batch([f"{m.question} {m.options[m.answer]}" for m in mcqs]))
    return [topics[int(i)] for i in (q_vecs @ topic_vecs.T).argmax(axis=1)]


def store_mcqs(db, topics: list[Topic], mcqs: list[MCQ], fixed: list[Topic] | None = None, reference: str = REFERENCE) -> int:
    if not mcqs:
        return 0
    targets = fixed or assign_topics(topics, mcqs)
    added = 0
    for mcq, topic in zip(mcqs, targets):
        digest = question_hash(mcq.question)
        exists = db.scalar(
            select(GeneratedQuestion.id).where(GeneratedQuestion.topic_id == topic.id, GeneratedQuestion.question_hash == digest)
        )
        if exists:
            continue
        db.add(GeneratedQuestion(
            topic_id=topic.id, question_text=mcq.question, options=mcq.options, correct_index=mcq.answer,
            explanation=mcq.explanation, source="notes", difficulty="medium", question_hash=digest,
            reference=reference[:500],
        ))
        added += 1
    return added


WITH_MCQS = False


def import_html_units(db, notes_dir: Path, course_name: str, mapping: dict, drops: dict[str, set[int]] | None) -> None:
    course = db.scalar(select(Course).where(Course.name == course_name))
    if course is None:
        raise LookupError(f"Course {course_name!r} not found — run scripts.seed_nrb first")
    for (paper, chapter_name), files in mapping.items():
        chapter = find_chapter(db, course, paper, chapter_name)
        topics = list(db.scalars(select(Topic).where(Topic.chapter_id == chapter.id).order_by(Topic.id)).all())
        chunks = added = total = 0
        for fname in files:
            notes = parse_notes_html(notes_dir / "notes_source" / fname, (drops or {}).get(fname))
            chunks += store_knowledge(db, chapter, f"Study notes · {notes.title} ({fname})", notes.sections)
            total += len(notes.mcqs)
            if WITH_MCQS:
                added += store_mcqs(db, topics, notes.mcqs, reference=f"Study notes · {notes.title}")
        db.flush()
        refresh_chapter_has_content(db, chapter.id)
        db.commit()
        print(f"  {course_name[:24]:<24} {chapter_name[:44]:<44} {chunks:>4} chunks  {added:>3}/{total:<3} MCQs")


def import_gk(db, notes_dir: Path) -> None:
    course = db.scalar(select(Course).where(Course.name == CO))
    sections, mcqs = parse_gk_pdf(notes_dir / GK_PDF)
    chapters = {k: find_chapter(db, course, "Part I", v) for k, v in GK_CHAPTERS.items()}
    topics = {k: list(db.scalars(select(Topic).where(Topic.chapter_id == c.id).order_by(Topic.id)).all()) for k, c in chapters.items()}

    # knowledge
    ga = [(f"Section {k}", v) for k, v in sections.items() if k.startswith("1.")]
    print(f"  GK notes: {store_knowledge(db, chapters['1'], 'Study notes · Lok Sewa Paper I master notes (Part A)', ga)} chunks for general awareness")
    for k in ("2.1", "2.2", "2.3"):
        if k in sections:
            store_knowledge(db, chapters[k], f"Study notes · Lok Sewa Paper I master notes ({k})", [(f"Section {k}", sections[k])])

    if not WITH_MCQS:
        db.flush()
        for c in chapters.values():
            refresh_chapter_has_content(db, c.id)
        db.commit()
        return
    # MCQs: practice "1.N" -> the N-th general-awareness topic; reasoning and model test by similarity
    added = 0
    ga_topics = topics["1"]
    exact = [m for m in mcqs if m.section and re.fullmatch(r"1\.\d+", m.section) and int(m.section.split(".")[1]) <= len(ga_topics)]
    ref = "Study notes · Lok Sewa Paper I master notes"
    added += store_mcqs(db, ga_topics, exact, fixed=[ga_topics[int(m.section.split(".")[1]) - 1] for m in exact], reference=ref)
    for sec in ("2.1", "2.2", "2.3"):
        added += store_mcqs(db, topics[sec], [m for m in mcqs if m.section == sec], reference=ref)
    added += store_mcqs(db, ga_topics, [m for m in mcqs if m.section == "model-A"], reference=f"{ref} · model test")
    reasoning = topics["2.1"] + topics["2.2"] + topics["2.3"]
    added += store_mcqs(db, reasoning, [m for m in mcqs if m.section == "model-B"], reference=f"{ref} · model test")
    db.flush()
    for c in chapters.values():
        refresh_chapter_has_content(db, c.id)
    db.commit()
    print(f"  GK MCQs: {added} added ({len(mcqs)} parsed: practice sets + model test)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--notes-dir", required=True, type=Path)
    parser.add_argument("--with-mcqs", action="store_true", help="also copy the MCQs written in the notes")
    args = parser.parse_args()
    global WITH_MCQS
    WITH_MCQS = args.with_mcqs
    notes_dir = args.notes_dir.expanduser()
    db = SessionLocal()
    try:
        print("NRB Assistant Director (IT):")
        import_html_units(db, notes_dir, AD, AD_MAP, drops=None)
        print("Computer Officer (Lok Sewa Aayog):")
        import_html_units(db, notes_dir, CO, CO_MAP, drops=co_drop_lists(notes_dir))
        import_gk(db, notes_dir)
    finally:
        db.close()


if __name__ == "__main__":
    main()
