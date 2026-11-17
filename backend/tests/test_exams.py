from datetime import timedelta

import pytest

from app.models import ExamAttempt, GeneratedQuestion
from app.services import exam_service
from app.services.syllabus_service import parse_syllabus

SYLLABUS = """
1. Computer Fundamentals [4]
- Number systems: binary, octal, hexadecimal
- Computer architecture: CPU, memory hierarchy
Unit 2: Networking
* OSI model: seven layers and their functions
1.1 Subnetting
# Database Management [2]
• SQL: DDL, DML, joins
"""


def test_parse_syllabus():
    chapters = parse_syllabus(SYLLABUS)
    assert [c.name for c in chapters] == ["Computer Fundamentals", "Networking", "Database Management"]
    assert [c.weight for c in chapters] == [4, None, 2]
    assert [t.name for t in chapters[1].topics] == ["OSI model", "Subnetting"]
    assert chapters[0].topics[0].detail == "binary, octal, hexadecimal"


@pytest.fixture()
def course(client, admin_headers):
    c = client.post(
        "/api/v1/courses",
        json={"name": "NRB Computer", "exam_name": "NRB Computer Officer", "exam_question_count": 8,
              "exam_duration_minutes": 10, "negative_marking": 0.25, "pass_percent": 50},
        headers=admin_headers,
    )
    assert c.status_code == 201, c.text
    r = client.post(f"/api/v1/courses/{c.json()['id']}/syllabus", json={"text": SYLLABUS}, headers=admin_headers)
    assert r.json() == {"chapters_created": 3, "topics_created": 5, "chapters_updated": 0, "topics_updated": 0}
    return c.json()


def _seed(db, client, admin_headers, course_id, per_topic=3):
    tree = client.get(f"/api/v1/courses/{course_id}", headers=admin_headers).json()
    n = 0
    for ch in tree["chapters"]:
        for t in ch["topics"]:
            for i in range(per_topic):
                n += 1
                db.add(GeneratedQuestion(topic_id=t["id"], question_text=f"{t['name']} question {i}?",
                                         options=["a", "b", "c", "d"], correct_index=0, explanation="x",
                                         source="groq", difficulty="medium"))
    db.commit()
    return tree


def test_syllabus_merge_replace_and_export(client, admin_headers, course):
    cid = course["id"]
    again = client.post(f"/api/v1/courses/{cid}/syllabus", json={"text": SYLLABUS}, headers=admin_headers).json()
    assert again["chapters_created"] == 0 and again["topics_created"] == 0  # idempotent merge

    text = client.get(f"/api/v1/courses/{cid}/syllabus", headers=admin_headers).json()["text"]
    assert "Computer Fundamentals [4]" in text and "- OSI model: seven layers and their functions" in text

    r = client.post(f"/api/v1/courses/{cid}/syllabus",
                    json={"text": "Networking [6]\n- OSI model\n- TCP/IP", "mode": "replace"}, headers=admin_headers)
    assert r.status_code == 200
    tree = client.get(f"/api/v1/courses/{cid}", headers=admin_headers).json()
    assert [c["name"] for c in tree["chapters"]] == ["Networking"]
    assert tree["chapters"][0]["weight"] == 6
    assert [t["name"] for t in tree["chapters"][0]["topics"]] == ["OSI model", "TCP/IP"]
    # existing topic kept its syllabus detail
    assert tree["chapters"][0]["topics"][0]["description"] == "seven layers and their functions"


def test_course_exam_settings_update(client, admin_headers, course):
    r = client.patch(f"/api/v1/courses/{course['id']}", json={"negative_marking": 0.2, "exam_duration_minutes": 30},
                     headers=admin_headers)
    assert r.json()["negative_marking"] == 0.2 and r.json()["exam_duration_minutes"] == 30
    assert r.json()["exam_name"] == "NRB Computer Officer"


def test_chapter_quotas_respect_weights():
    class C:
        def __init__(self, id, weight):
            self.id, self.weight = id, weight

    quotas = exam_service.chapter_quotas([C(1, 4), C(2, 0), C(3, 2), C(4, 0)], 10)
    assert quotas == {1: 4, 2: 2, 3: 2, 4: 2}


def test_mock_exam_full_flow(client, db, admin_headers, student_headers, course):
    cid = course["id"]
    assert client.post(f"/api/v1/courses/{cid}/mock-exams", headers=student_headers).status_code == 422  # empty bank

    _seed(db, client, admin_headers, cid)
    ready = client.get(f"/api/v1/courses/{cid}/readiness", headers=student_headers).json()
    assert ready["paper_size"] == 8 and ready["is_ready"] is True
    by_name = {c["chapter_name"]: c for c in ready["chapters"]}
    assert by_name["Computer Fundamentals"]["needed"] == 4 and by_name["Networking"]["needed"] == 2

    exam = client.post(f"/api/v1/courses/{cid}/mock-exams", headers=student_headers).json()
    assert exam["status"] == "in_progress" and len(exam["questions"]) == 8
    assert "correct_index" not in exam["questions"][0] and exam["questions"][0]["chapter_name"]

    # resuming returns the same attempt
    again = client.post(f"/api/v1/courses/{cid}/mock-exams", headers=student_headers).json()
    assert again["id"] == exam["id"]

    # autosave, then submit: 5 right (index 0), 2 wrong, 1 skipped
    answers = [0, 0, 0, 0, 0, 1, 2, None]
    save = client.put(f"/api/v1/mock-exams/{exam['id']}/progress", json={"answers": answers, "flagged": [2]},
                      headers=student_headers)
    assert save.status_code == 200
    resumed = client.get(f"/api/v1/mock-exams/{exam['id']}", headers=student_headers).json()
    assert resumed["answers"] == answers and resumed["flagged"] == [2]

    result = client.post(f"/api/v1/mock-exams/{exam['id']}/submit", json={"answers": answers, "flagged": []},
                         headers=student_headers).json()
    assert (result["correct"], result["wrong"], result["skipped"]) == (5, 2, 1)
    assert result["score"] == 4.5  # 5 - 0.25 * 2
    assert result["percent"] == 56.2 and result["passed"] is True
    assert result["questions"][0]["correct_index"] == 0
    assert sum(b["total"] for b in result["chapter_breakdown"]) == 8

    # cannot change after submission; admin can view, other student cannot
    assert client.put(f"/api/v1/mock-exams/{exam['id']}/progress", json={"answers": []},
                      headers=student_headers).status_code == 409
    assert client.get(f"/api/v1/mock-exams/{exam['id']}", headers=admin_headers).status_code == 200
    history = client.get("/api/v1/mock-exams/me", headers=student_headers).json()
    assert history[0]["score"] == 4.5 and history[0]["passed"] is True


def test_late_submission_uses_saved_answers(client, db, admin_headers, student_headers, course):
    _seed(db, client, admin_headers, course["id"])
    exam = client.post(f"/api/v1/courses/{course['id']}/mock-exams", headers=student_headers).json()
    client.put(f"/api/v1/mock-exams/{exam['id']}/progress", json={"answers": [0] * 2}, headers=student_headers)

    attempt = db.get(ExamAttempt, exam["id"])
    attempt.started_at = attempt.started_at - timedelta(minutes=30)  # 10-minute exam, long over
    db.commit()

    # Reading an expired exam auto-submits it with what was saved.
    result = client.get(f"/api/v1/mock-exams/{exam['id']}", headers=student_headers).json()
    assert result["status"] == "submitted" and result["correct"] == 2 and result["skipped"] == 6


def test_branding_and_signup_toggle(client, admin_headers, student_headers):
    assert client.get("/api/v1/settings/branding").json()["institution_name"] == "QuizForge"
    r = client.put("/api/v1/settings/branding",
                   json={"institution_name": "Kathmandu Exam Academy", "primary_color": "#0f766e",
                         "accent_color": "#b45309", "tagline": "Crack NRB", "allow_signup": False},
                   headers=admin_headers)
    assert r.status_code == 200
    assert client.get("/api/v1/settings/branding").json()["institution_name"] == "Kathmandu Exam Academy"
    assert client.put("/api/v1/settings/branding", json={"institution_name": "x"}, headers=student_headers).status_code == 403
    blocked = client.post("/api/v1/auth/register", json={"email": "new@x.com", "password": "secret123"})
    assert blocked.status_code == 403
    bad_color = client.put("/api/v1/settings/branding", json={"primary_color": "red"}, headers=admin_headers)
    assert bad_color.status_code == 422


def test_weak_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": "a@x.com", "password": "onlyletters"})
    assert r.status_code == 422


def test_login_throttled_after_repeated_failures(client, admin_headers):
    for _ in range(8):
        client.post("/api/v1/auth/login", data={"username": "throttle@x.com", "password": "wrongpass1"})
    r = client.post("/api/v1/auth/login", data={"username": "throttle@x.com", "password": "wrongpass1"})
    assert r.status_code == 429


def test_security_headers(client):
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Request-ID"]


def test_pipeline_endpoints_queue_tasks(client, admin_headers, student_headers, course, monkeypatch):
    from app.workers import research_worker

    class T:
        id = "t-1"

    calls = []
    monkeypatch.setattr(research_worker.build_course_bank_task, "delay", lambda **kw: calls.append(kw) or T())
    monkeypatch.setattr(research_worker.research_topic_task, "delay", lambda **kw: calls.append(kw) or T())
    r = client.post(f"/api/v1/courses/{course['id']}/build-bank", json={"per_topic": 9}, headers=admin_headers)
    assert r.status_code == 202 and calls[-1] == {"course_id": course["id"], "per_topic": 9, "research": True}
    tree = client.get(f"/api/v1/courses/{course['id']}", headers=admin_headers).json()
    tid = tree["chapters"][0]["topics"][0]["id"]
    assert client.post(f"/api/v1/topics/{tid}/research", headers=admin_headers).status_code == 202
    assert client.post(f"/api/v1/topics/{tid}/research", headers=student_headers).status_code == 403


def test_build_bank_task_researches_and_generates(db_session_factory, client, admin_headers, course, monkeypatch):
    from app.workers import research_worker

    monkeypatch.setattr(research_worker, "SessionLocal", db_session_factory)
    researched = []
    monkeypatch.setattr(research_worker, "research_topic_now",
                        lambda db, topic: researched.append(topic.name) or {"topic_id": topic.id, "sources": 2, "stored": 2})
    generated = []

    def fake_generate(db, topic_id, count, difficulty, allow_web_fallback):
        generated.append((topic_id, count, difficulty))
        return {"generated": count, "source": "groq",
                "questions": [{"difficulty": ("easy", "medium", "hard")[i % 3]} for i in range(count)]}

    monkeypatch.setattr(research_worker, "generate_for_topic", fake_generate)
    monkeypatch.setattr(research_worker.build_course_bank_task, "update_state", lambda **kw: None)
    result = research_worker.build_course_bank_task.run(course_id=course["id"], per_topic=6)
    assert result["topics"] == 5 and result["researched"] == 5
    assert result["generated"] == 5 * 6
    assert len(generated) == 5 and {d for _, _, d in generated} == {"mixed"}  # one call per topic


def test_bank_job_is_tracked_and_not_duplicated(client, admin_headers, course, monkeypatch):
    from app.utils import task_status
    from app.workers import research_worker

    class T:
        id = "job-1"

    monkeypatch.setattr(research_worker.build_course_bank_task, "delay", lambda **kw: T())
    assert client.get(f"/api/v1/courses/{course['id']}/build-bank", headers=admin_headers).json() == {"job": None}
    assert client.post(f"/api/v1/courses/{course['id']}/build-bank", json={}, headers=admin_headers).status_code == 202

    monkeypatch.setattr(task_status, "task_status_payload",
                        lambda tid: {"task_id": tid, "state": "PROGRESS", "result": None, "error": None, "progress": {"done": 1, "total": 5}})
    job = client.get(f"/api/v1/courses/{course['id']}/build-bank", headers=admin_headers).json()["job"]
    assert job["task_id"] == "job-1" and job["progress"]["done"] == 1
    assert client.post(f"/api/v1/courses/{course['id']}/build-bank", json={}, headers=admin_headers).status_code == 409


PAPERS = """
Paper I: Information Technology I
Computer Architecture [3]
- Basic structures: RISC, CISC
Operating Systems [2]
- Processes and threads
Paper II: Information Technology II
Programming Language [3]
- Paradigms
Operating Systems [2]
- Shell scripting
"""


def test_syllabus_with_papers_round_trips(client, admin_headers):
    c = client.post("/api/v1/courses", json={"name": "AD", "exam_question_count": 5, "exam_duration_minutes": 30},
                    headers=admin_headers).json()
    r = client.post(f"/api/v1/courses/{c['id']}/syllabus", json={"text": PAPERS}, headers=admin_headers).json()
    # "Operating Systems" exists in both papers -> two separate chapters
    assert r["chapters_created"] == 4 and r["topics_created"] == 4
    tree = client.get(f"/api/v1/courses/{c['id']}", headers=admin_headers).json()
    assert [ch["paper"] for ch in tree["chapters"]] == ["Paper I: Information Technology I"] * 2 + ["Paper II: Information Technology II"] * 2
    text = client.get(f"/api/v1/courses/{c['id']}/syllabus", headers=admin_headers).json()["text"]
    assert text.splitlines()[0] == "Paper I: Information Technology I" and "Paper II: Information Technology II" in text
    again = client.post(f"/api/v1/courses/{c['id']}/syllabus", json={"text": text}, headers=admin_headers).json()
    assert again["chapters_created"] == 0 and again["topics_created"] == 0


def test_mock_exam_per_paper_and_full(client, db, admin_headers, student_headers):
    c = client.post("/api/v1/courses", json={"name": "AD", "exam_question_count": 5, "exam_duration_minutes": 30},
                    headers=admin_headers).json()
    client.post(f"/api/v1/courses/{c['id']}/syllabus", json={"text": PAPERS}, headers=admin_headers)
    _seed(db, client, admin_headers, c["id"], per_topic=6)
    p1 = "Paper I: Information Technology I"

    ready = client.get(f"/api/v1/courses/{c['id']}/readiness", params={"paper": p1}, headers=student_headers).json()
    assert ready["paper_size"] == 5 and ready["papers"] == [p1, "Paper II: Information Technology II"]
    assert client.get(f"/api/v1/courses/{c['id']}/readiness", params={"paper": "Paper IX"}, headers=student_headers).status_code == 404

    exam = client.post(f"/api/v1/courses/{c['id']}/mock-exams", json={"paper": p1}, headers=student_headers).json()
    assert exam["paper"] == p1 and len(exam["questions"]) == 5 and exam["time_limit_seconds"] == 30 * 60
    assert {q["chapter_name"] for q in exam["questions"]} <= {"Computer Architecture", "Operating Systems"}

    full = client.post(f"/api/v1/courses/{c['id']}/mock-exams", json={}, headers=student_headers).json()
    assert full["id"] != exam["id"] and full["paper"] is None
    assert len(full["questions"]) == 10 and full["time_limit_seconds"] == 2 * 30 * 60


def test_past_paper_extraction_and_sources(client, db, admin_headers, course, monkeypatch, tmp_path):
    import json
    from pathlib import Path

    from app.models import Course
    from app.services import past_paper_service

    extracted = {"questions": [
        {"question": "Which layer of the OSI model handles routing?", "options": ["Physical", "Network", "Session", "Data link"],
         "correct_index": 1, "explanation": "Routing is a network-layer function.", "difficulty": "easy"},
        {"question": "What does DDL stand for in SQL?", "options": ["Data Definition Language", "Data Driven Logic", "Direct Data Link", "Dynamic Data Load"],
         "correct_index": 0, "explanation": "DDL defines schema objects.", "difficulty": "easy"},
    ]}
    prompts = []
    monkeypatch.setattr(past_paper_service, "generate",
                        lambda prompt, providers=None: prompts.append(prompt) or {"raw": json.dumps(extracted), "source": "groq", "model": "m"})
    paper = tmp_path / "nrb_2081.txt"
    paper.write_text("1. Which layer of the OSI model handles routing? (a) Physical (b) Network ... Ans: b\n" * 3)

    c = db.get(Course, course["id"])
    result = past_paper_service.import_past_paper(db, c, Path(paper), "NRB AD 2081 Paper I")
    assert result["added"] == 2 and result["ocr"] is False
    assert "NRB Computer Officer" in prompts[0]  # exam name steers extraction

    again = past_paper_service.import_past_paper(db, c, Path(paper), "NRB AD 2081 Paper I")
    assert again["added"] == 0 and again["duplicates"] == 2  # never imported twice

    tree = client.get(f"/api/v1/courses/{course['id']}", headers=admin_headers).json()
    by_topic = {t["name"]: t["question_count"] for ch in tree["chapters"] for t in ch["topics"]}
    assert by_topic["OSI model"] == 1 and by_topic["SQL"] == 1  # filed under the right topics

    src = client.get(f"/api/v1/courses/{course['id']}/question-sources", headers=admin_headers).json()
    assert src["by_kind"] == {"past_paper": 2}
    assert src["references"][0] == {"kind": "past_paper", "reference": "NRB AD 2081 Paper I", "count": 2}


def test_past_paper_upload_endpoint(client, admin_headers, student_headers, course, monkeypatch):
    from app.workers import research_worker

    class T:
        id = "pp-1"

    sent = {}
    monkeypatch.setattr(research_worker.process_past_paper_task, "delay", lambda **kw: sent.update(kw) or T())
    bad = client.post(f"/api/v1/courses/{course['id']}/past-papers", data={"label": "x2"},
                      files={"file": ("paper.exe", b"MZ", "application/octet-stream")}, headers=admin_headers)
    assert bad.status_code == 400
    ok = client.post(f"/api/v1/courses/{course['id']}/past-papers", data={"label": "LSC 2079 Paper I"},
                     files={"file": ("scan.png", b"\x89PNG....", "image/png")}, headers=admin_headers)
    assert ok.status_code == 202 and ok.json()["paper_id"] == sent["paper_id"]
    papers = client.get(f"/api/v1/courses/{course['id']}/past-papers", headers=admin_headers).json()["papers"]
    assert papers[0]["title"] == "LSC 2079 Paper I" and papers[0]["source"] == "upload" and papers[0]["status"] == "found"
    # students only see papers that have been read
    assert client.get(f"/api/v1/courses/{course['id']}/past-papers", headers=student_headers).json()["papers"] == []
    assert client.post(f"/api/v1/courses/{course['id']}/collect-online", headers=student_headers).status_code == 403


def test_exam_writes_missing_questions_when_bank_runs_out(client, db, db_session_factory, admin_headers, student_headers, course, monkeypatch):
    from app.config import settings
    from app.models import GeneratedQuestion
    from app.services import exam_service

    _seed(db, client, admin_headers, course["id"], per_topic=1)  # 5 questions, paper needs 8
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    calls = {}

    def fake_write(factory, short, budget_seconds=45.0):
        calls["short"] = dict(short)
        s = db_session_factory()
        from app.models import Topic
        n = 0
        for chapter_id, missing in short.items():
            topic = s.query(Topic).filter(Topic.chapter_id == chapter_id).first()
            for i in range(missing):
                s.add(GeneratedQuestion(topic_id=topic.id, question_text=f"AI question {chapter_id}-{i} on {topic.name}?",
                                        options=["a", "b", "c", "d"], correct_index=0, explanation="x", source="groq"))
                n += 1
        s.commit()
        s.close()
        return n

    monkeypatch.setattr(exam_service, "write_missing_questions", fake_write)
    exam = client.post(f"/api/v1/courses/{course['id']}/mock-exams", headers=student_headers).json()
    assert sum(calls["short"].values()) == 3  # Computer Fundamentals needs 4 but has 2 unseen -> short 2; DBMS 2 vs 1 -> short 1
    assert exam["fresh_generated"] == 3 and len(exam["questions"]) == 8
    assert sum(q["question_text"].startswith("AI question") for q in exam["questions"]) == 3


def test_write_missing_questions_respects_time_budget(monkeypatch):
    import time

    from app.services import exam_service, quiz_service

    class FakeDB:
        def execute(self, *a, **k):
            class R:
                def all(self_inner):
                    return [(1, 0)]
            return R()

        def rollback(self):
            pass

        def close(self):
            pass

    def slow(db, topic_id, count, difficulty, **kw):
        time.sleep(3)
        return {"generated": count}

    monkeypatch.setattr(quiz_service, "generate_for_topic", slow)
    started = time.monotonic()
    n = exam_service.write_missing_questions(lambda: FakeDB(), {1: 5}, budget_seconds=0.5)
    assert time.monotonic() - started < 1.5  # the student is not kept waiting for the slow model
    assert n == 0


THREE_PAPERS = """
Paper I: IT I
Architecture [5]
- CPU design
Paper II: IT II
Programming [5]
- Paradigms
Paper III: Emerging
Cloud [5]
- Cloud basics
"""


def _three_paper_course(client, db, admin_headers, **pattern):
    c = client.post("/api/v1/courses", json={"name": "NRB AD", "exam_question_count": 5, "exam_duration_minutes": 30,
                                              "negative_marking": 0.2, "pass_percent": 40, **pattern},
                    headers=admin_headers).json()
    client.post(f"/api/v1/courses/{c['id']}/syllabus", json={"text": THREE_PAPERS}, headers=admin_headers)
    _seed(db, client, admin_headers, c["id"], per_topic=8)
    return c


def test_full_exam_has_one_section_per_paper(client, db, admin_headers, student_headers):
    c = _three_paper_course(client, db, admin_headers)
    exam = client.post(f"/api/v1/courses/{c['id']}/mock-exams", json={}, headers=student_headers).json()
    assert exam["time_limit_seconds"] == 90 * 60
    assert [(s["paper"], s["start"], s["count"], s["minutes"]) for s in exam["sections"]] == [
        ("Paper I: IT I", 0, 5, 30), ("Paper II: IT II", 5, 5, 30), ("Paper III: Emerging", 10, 5, 30)]
    # sections never mix: each block holds only its own paper's chapter
    assert {q["chapter_name"] for q in exam["questions"][0:5]} == {"Architecture"}
    assert {q["chapter_name"] for q in exam["questions"][5:10]} == {"Programming"}
    assert {q["chapter_name"] for q in exam["questions"][10:15]} == {"Cloud"}
    assert exam["marking"]["lines"][-1].startswith("Pass mark: 40% in EACH paper")


def test_per_paper_pass_rule_fails_if_any_paper_fails(client, db, admin_headers, student_headers):
    c = _three_paper_course(client, db, admin_headers, pass_rule="per_paper")
    exam = client.post(f"/api/v1/courses/{c['id']}/mock-exams", json={}, headers=student_headers).json()
    # seeded answer is always index 0: ace papers I and II, skip paper III
    answers = [0] * 10 + [None] * 5
    r = client.post(f"/api/v1/mock-exams/{exam['id']}/submit", json={"answers": answers}, headers=student_headers).json()
    assert [s["percent"] for s in r["section_results"]] == [100.0, 100.0, 0.0]
    assert [s["passed"] for s in r["section_results"]] == [True, True, False]
    assert r["percent"] == 66.7 and r["passed"] is False  # 66.7% overall, but Paper III failed


def test_overall_pass_rule_and_marks_per_question(client, db, admin_headers, student_headers):
    c = _three_paper_course(client, db, admin_headers, pass_rule="overall", marks_per_question=2)
    exam = client.post(f"/api/v1/courses/{c['id']}/mock-exams", json={}, headers=student_headers).json()
    answers = [0] * 10 + [1] * 5  # 10 right, 5 wrong
    r = client.post(f"/api/v1/mock-exams/{exam['id']}/submit", json={"answers": answers}, headers=student_headers).json()
    assert r["score"] == 2 * 10 - 0.2 * 2 * 5 == 18.0 and r["max_score"] == 30
    assert r["percent"] == 60.0 and r["passed"] is True  # combined score decides
    assert r["section_results"][2]["score"] == -2.0 and r["section_results"][2]["passed"] is False
    assert exam["marking"]["lines"][0] == "Each correct answer: +2 marks." and "−0.4 mark" in exam["marking"]["lines"][1]


def test_mcq_detection_tolerates_ocr_noise():
    from app.services.paper_finder import looks_like_mcq

    ocr = ("1. Which page replacement algorithm suffers from Belady's anomaly?\n(9) LRU (0) Optimal (c) FIFO (d) LFU\n\n"
           "2. A relation in BCNF is always in:\n(a) INF only (0) 3NF (c) 4NF (d) 5NF\n")
    assert looks_like_mcq(ocr)
    essay = "Section A\n1. Write an essay in about 800 words on foreign employment and its impact on the economy.\n" * 3
    assert not looks_like_mcq(essay)


def test_extraction_failure_is_not_reported_as_subjective(monkeypatch):
    from app.services import past_paper_service
    from app.services.generation_service import GenerationError

    def down(prompt, providers=None):
        raise GenerationError("All LLM providers failed")

    monkeypatch.setattr(past_paper_service, "generate", down)
    with pytest.raises(GenerationError):
        past_paper_service.extract_mcqs("1. Q? (a) x (b) y (c) z (d) w", "NRB")
