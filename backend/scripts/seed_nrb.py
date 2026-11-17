"""Create the two courses from the official syllabi in ``scripts/syllabi/`` (idempotent).

    venv/bin/python -m scripts.seed_nrb                 # create or merge
    venv/bin/python -m scripts.seed_nrb --reset         # delete and recreate both courses
    venv/bin/python -m scripts.seed_nrb --remove-sample-data

Sources (the candidate's NRB folder):
* NRB Assistant Director (IT), Officer 3rd Class — official syllabus approved 2080/05/07.
  Three written papers; the objective part of EACH paper is 25 MCQ × 1 mark,
  30 minutes, 0.2 marks deducted per wrong answer. Chapter weights = the
  official MCQ count per unit.
* Lok Sewa Aayog Computer Officer, Gazetted 3rd Class — syllabus effective 2080/07/20.
  Paper I (objective) = Part I General Awareness & Reasoning (50 MCQ) +
  Part II General Technical Subject (50 MCQ), 1 hr 30 min, 20% negative marking.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Course
from app.services.syllabus_service import import_syllabus
from app.utils.cleanup import delete_course, purge_topic_artifacts

SYLLABI = Path(__file__).resolve().parent / "syllabi"

COURSES = [
    dict(
        name="NRB Assistant Director (IT)",
        exam_name="Nepal Rastra Bank — Assistant Director (Information Technology), Officer 3rd Class",
        description=(
            "Objective-paper preparation for the NRB Assistant Director (IT) open competition: "
            "Paper I (IT I), Paper II (IT II) and Paper III (current developments & emerging technologies), "
            "following the official 2080 syllabus and its MCQ distribution per unit."
        ),
        syllabus="nrb_ad_it.txt",
        exam_question_count=25,   # per paper
        exam_duration_minutes=30,  # per paper
        negative_marking=0.2,
        pass_percent=40,
        marks_per_question=1.0,
        pass_rule="per_paper",  # official scheme: pass marks 40 in each paper
        exam_instructions=(
            "• Objective part of each paper: 25 multiple-choice questions × 1 mark, 30 minutes.\n"
            "• 0.2 marks are deducted for each wrong answer; unanswered questions score zero.\n"
            "• No calculator. Questions are in English.\n"
            "• Choose one paper, or take all three papers together: one 90-minute sitting with three sections\n"
            "  (Paper I, II, III), 30 minutes suggested for each; every paper is marked and passed separately.\n"
            "• The test is submitted automatically when the time is over."
        ),
        publish=True,
    ),
    dict(
        name="Computer Officer (Lok Sewa Aayog)",
        exam_name="Lok Sewa Aayog — Computer Officer, Gazetted 3rd Class (Paper I, objective)",
        description=(
            "Preparation for the Lok Sewa Aayog Computer Officer exam (Nepal Miscellaneous Service): "
            "Part I general awareness & reasoning and Part II general technical subject (IT), "
            "with the official unit weightage."
        ),
        syllabus="lsc_computer_officer.txt",
        exam_question_count=50,   # per part
        exam_duration_minutes=45,  # per part; the full Paper I is 100 MCQ in 90 minutes
        negative_marking=0.2,
        pass_percent=40,
        marks_per_question=1.0,
        pass_rule="overall",  # Paper I is one paper: 100 full marks, pass marks 40 overall
        exam_instructions=(
            "• Paper I has two parts: Part I General Awareness & Reasoning (50 MCQ) and Part II IT (50 MCQ).\n"
            "• The full paper is 100 questions in 1 hour 30 minutes; a single part is 50 questions in 45 minutes.\n"
            "• Each wrong answer loses 20% of its mark (0.2); unanswered questions score zero.\n"
            "• No calculator.\n"
            "• The test is submitted automatically when the time is over."
        ),
        publish=True,
    ),
]

OLD_NAMES = ("NRB Computer Officer",)  # draft course from an earlier version


def seed(reset: bool = False, remove_sample_data: bool = False) -> None:
    db = SessionLocal()
    try:
        drop = list(OLD_NAMES)
        if remove_sample_data:
            drop += [n for n in db.scalars(select(Course.name).where(Course.name.like("Biology%"))).all()]
        if reset:
            drop += [c["name"] for c in COURSES]
        for course_id, name in db.execute(select(Course.id, Course.name).where(Course.name.in_(drop))).all():
            purge_topic_artifacts(delete_course(db, course_id))
            db.commit()
            print(f"Removed course {name!r}")

        for spec in COURSES:
            text = (SYLLABI / spec["syllabus"]).read_text(encoding="utf-8")
            course = db.scalar(select(Course).where(Course.name == spec["name"]))
            fields = {k: spec[k] for k in ("exam_name", "description", "exam_question_count", "exam_duration_minutes",
                                          "negative_marking", "pass_percent", "exam_instructions",
                                          "marks_per_question", "pass_rule")}
            if course is None:
                course = Course(name=spec["name"], is_published=spec["publish"], **fields)
                db.add(course)
                db.flush()
                print(f"Created course {spec['name']!r} (id={course.id})")
            else:
                for key, value in fields.items():
                    setattr(course, key, value)
            counts, _ = import_syllabus(db, course.id, text, replace=False)
            db.commit()
            print(f"  {spec['name']}: {counts}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete and recreate both courses")
    parser.add_argument("--remove-sample-data", action="store_true", help="delete the Biology demo course")
    args = parser.parse_args()
    seed(reset=args.reset, remove_sample_data=args.remove_sample_data)
