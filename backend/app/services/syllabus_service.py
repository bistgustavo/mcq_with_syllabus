"""Import/export a course syllabus as a plain-text outline.

Format (forgiving, so an official syllabus can be pasted with light editing)::

    1. Computer Fundamentals [10]
    - Number systems: binary, octal, hexadecimal, conversions
    - Computer architecture: CPU, memory hierarchy, I/O
    Networking [8]
    * OSI and TCP/IP models
    1.1 Subnetting

* A chapter is any line that is not a topic line. Leading "#", "1.", "Unit 2:",
  "Chapter 3 -" etc. are stripped. A trailing "[N]" sets the chapter weight
  (questions it contributes to a full mock paper).
* A topic line starts with "-", "*", "•", "–" or a dotted number like "1.1".
  Text after the first ":" becomes the topic's syllabus detail, which guides
  web research and question generation.

Merge mode updates matching chapters/topics (case-insensitive by name) and
adds new ones. Replace mode additionally deletes chapters/topics that are no
longer listed. Existing topics keep their notes and questions either way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chapter, Topic
from app.utils.cleanup import delete_chapters, delete_topics

_TOPIC_RE = re.compile(r"^\s*(?:[-*•–·]|\d+\.\d+[.)]?)\s+(.*)$")
_CHAPTER_PREFIX_RE = re.compile(
    r"^\s*(?:#+\s*|(?:unit|chapter|section|part|paper)\s*[\dIVXivx]*\s*[:.\-–)]?\s*|\d+\s*[.)\-:]\s*|[IVX]+\s*[.)]\s*)",
    re.IGNORECASE,
)
_WEIGHT_RE = re.compile(r"\s*\[(\d{1,3})\]\s*$")
# "Paper I: Information Technology I", "== Part II — General Technical Subject ==", "PAPER 3"
_PAPER_RE = re.compile(r"^\s*=*\s*((?:paper|part)\s+(?:[IVX]+|\d+)\b.*?)\s*=*\s*$", re.IGNORECASE)


@dataclass
class ParsedTopic:
    name: str
    detail: str | None = None


@dataclass
class ParsedChapter:
    name: str
    weight: int | None = None
    paper: str | None = None
    topics: list[ParsedTopic] = field(default_factory=list)


def _clean(text: str, limit: int = 255) -> str:
    return re.sub(r"\s+", " ", text).strip(" \t-–:;,.")[:limit].strip()


def parse_syllabus(text: str) -> list[ParsedChapter]:
    chapters: list[ParsedChapter] = []
    paper: str | None = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        paper_match = _PAPER_RE.match(raw)
        if paper_match and not _TOPIC_RE.match(raw):
            paper = re.sub(r"\s+", " ", paper_match.group(1)).strip(" :-–—")[:255]
            continue
        topic_match = _TOPIC_RE.match(raw)
        if topic_match:
            body = topic_match.group(1)
            name, _, detail = body.partition(":")
            name = _clean(name)
            if not name:
                continue
            if not chapters:
                chapters.append(ParsedChapter(name="General", paper=paper))
            chapters[-1].topics.append(ParsedTopic(name=name, detail=_clean(detail, 4000) or None))
            continue

        line = raw.strip()
        weight = None
        weight_match = _WEIGHT_RE.search(line)
        if weight_match:
            weight = int(weight_match.group(1))
            line = line[: weight_match.start()]
        name = _clean(_CHAPTER_PREFIX_RE.sub("", line, count=1))
        if name:
            chapters.append(ParsedChapter(name=name, weight=weight, paper=paper))
    return chapters


def import_syllabus(db: Session, course_id: int, text: str, replace: bool = False) -> tuple[dict, list[int]]:
    """Apply the outline to the course. Returns (counts, removed_topic_ids). Does not commit."""
    parsed = parse_syllabus(text)
    def ckey(name: str, paper: str | None) -> str:
        return f"{(paper or '').lower()}::{name.lower()}"

    existing = {ckey(c.name, c.paper): c for c in db.scalars(select(Chapter).where(Chapter.course_id == course_id)).all()}
    counts = {"chapters_created": 0, "topics_created": 0, "chapters_updated": 0, "topics_updated": 0}
    keep_chapter_ids: set[int] = set()
    keep_topic_ids: set[int] = set()

    next_order = (db.scalar(select(func.max(Chapter.order)).where(Chapter.course_id == course_id)) or -1) + 1
    for index, pc in enumerate(parsed):
        chapter = existing.get(ckey(pc.name, pc.paper))
        if chapter is None:
            chapter = Chapter(
                course_id=course_id, name=pc.name, order=index if replace else next_order,
                weight=pc.weight or 0, paper=pc.paper,
            )
            next_order += 1
            db.add(chapter)
            db.flush()
            existing[ckey(pc.name, pc.paper)] = chapter
            counts["chapters_created"] += 1
        else:
            changed = False
            if pc.weight is not None and chapter.weight != pc.weight:
                chapter.weight, changed = pc.weight, True
            if replace and chapter.order != index:
                chapter.order, changed = index, True
            counts["chapters_updated"] += int(changed)
        keep_chapter_ids.add(chapter.id)

        topics = {t.name.lower(): t for t in db.scalars(select(Topic).where(Topic.chapter_id == chapter.id)).all()}
        for pt in pc.topics:
            topic = topics.get(pt.name.lower())
            if topic is None:
                topic = Topic(chapter_id=chapter.id, name=pt.name, description=pt.detail)
                db.add(topic)
                db.flush()
                topics[pt.name.lower()] = topic
                counts["topics_created"] += 1
            elif pt.detail and topic.description != pt.detail:
                topic.description = pt.detail
                counts["topics_updated"] += 1
            keep_topic_ids.add(topic.id)

    removed: list[int] = []
    if replace and parsed:
        all_chapters = db.scalars(select(Chapter).where(Chapter.course_id == course_id)).all()
        drop_chapters = [c.id for c in all_chapters if c.id not in keep_chapter_ids]
        removed += delete_chapters(db, drop_chapters)
        stale_topics = db.scalars(
            select(Topic.id).where(Topic.chapter_id.in_(keep_chapter_ids), Topic.id.not_in(keep_topic_ids))
        ).all()
        delete_topics(db, list(stale_topics))
        removed += list(stale_topics)
    db.flush()
    return counts, removed


def export_syllabus(db: Session, course_id: int) -> str:
    chapters = db.scalars(
        select(Chapter).where(Chapter.course_id == course_id).order_by(Chapter.order, Chapter.id)
    ).all()
    lines: list[str] = []
    current_paper: str | None = None
    for chapter in chapters:
        if chapter.paper and chapter.paper != current_paper:
            if lines:
                lines.append("")
            lines.append(chapter.paper)
            current_paper = chapter.paper
        if lines:
            lines.append("")
        lines.append(f"{chapter.name} [{chapter.weight}]" if chapter.weight else chapter.name)
        for topic in db.scalars(select(Topic).where(Topic.chapter_id == chapter.id).order_by(Topic.id)).all():
            lines.append(f"- {topic.name}: {topic.description}" if topic.description else f"- {topic.name}")
    return "\n".join(lines)
