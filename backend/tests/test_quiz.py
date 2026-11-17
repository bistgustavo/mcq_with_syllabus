def test_start_quiz_hides_answers(client, student_headers, topic, seeded_questions):
    r = client.get(f"/api/v1/topics/{topic['id']}/quiz?count=4", headers=student_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["available"] == 4
    for q in body["questions"]:
        assert "correct_index" not in q and "explanation" not in q


def test_quiz_difficulty_filter(client, student_headers, topic, seeded_questions):
    body = client.get(f"/api/v1/topics/{topic['id']}/quiz?count=10&difficulty=hard", headers=student_headers).json()
    assert body["available"] == 3
    assert all(q["difficulty"] == "hard" for q in body["questions"])


def test_unseen_questions_come_first(client, student_headers, topic, seeded_questions):
    first = client.get(f"/api/v1/topics/{topic['id']}/quiz?count=3", headers=student_headers).json()
    ids = [q["id"] for q in first["questions"]]
    client.post(
        "/api/v1/quiz-attempts",
        json={"topic_id": topic["id"], "answers": [{"question_id": i, "selected_index": 0} for i in ids]},
        headers=student_headers,
    )
    second = client.get(f"/api/v1/topics/{topic['id']}/quiz?count=3", headers=student_headers).json()
    assert not set(ids) & {q["id"] for q in second["questions"]}


def test_submit_scores_on_server(client, student_headers, topic, seeded_questions):
    # correct_index of seeded question i is i % 4
    answers = [
        {"question_id": seeded_questions[0], "selected_index": 0},  # correct
        {"question_id": seeded_questions[1], "selected_index": 0},  # wrong
        {"question_id": seeded_questions[2], "selected_index": None},  # skipped
    ]
    r = client.post(
        "/api/v1/quiz-attempts",
        json={"topic_id": topic["id"], "answers": answers, "difficulty": "easy", "duration_seconds": 42},
        headers=student_headers,
    )
    assert r.status_code == 201, r.text
    result = r.json()
    assert (result["score"], result["total"], result["percent"]) == (1, 3, 33.3)
    assert [x["is_correct"] for x in result["results"]] == [True, False, False]

    again = client.get(f"/api/v1/quiz-attempts/{result['attempt_id']}", headers=student_headers).json()
    assert again["score"] == 1 and again["results"][1]["selected_index"] == 0

    history = client.get("/api/v1/quiz-attempts/me", headers=student_headers).json()
    assert history[0]["topic_name"] == "Mitochondria" and history[0]["course_name"] == "Biology"


def test_submit_rejects_foreign_or_duplicate_questions(client, admin_headers, student_headers, topic, seeded_questions):
    other = client.post("/api/v1/topics", json={"chapter_id": topic["chapter_id"], "name": "Ribosomes"}, headers=admin_headers).json()
    r = client.post(
        "/api/v1/quiz-attempts",
        json={"topic_id": other["id"], "answers": [{"question_id": seeded_questions[0], "selected_index": 1}]},
        headers=student_headers,
    )
    assert r.status_code == 422
    dup = client.post(
        "/api/v1/quiz-attempts",
        json={
            "topic_id": topic["id"],
            "answers": [
                {"question_id": seeded_questions[0], "selected_index": 1},
                {"question_id": seeded_questions[0], "selected_index": 2},
            ],
        },
        headers=student_headers,
    )
    assert dup.status_code == 422
    bad_index = client.post(
        "/api/v1/quiz-attempts",
        json={"topic_id": topic["id"], "answers": [{"question_id": seeded_questions[0], "selected_index": 7}]},
        headers=student_headers,
    )
    assert bad_index.status_code == 422


def test_attempts_are_private(client, admin_headers, student_headers, topic, seeded_questions):
    r = client.post(
        "/api/v1/quiz-attempts",
        json={"topic_id": topic["id"], "answers": [{"question_id": seeded_questions[0], "selected_index": 0}]},
        headers=admin_headers,
    ).json()
    assert client.get(f"/api/v1/quiz-attempts/{r['attempt_id']}", headers=student_headers).status_code == 404


def test_dashboard(client, student_headers, topic, seeded_questions):
    for selected in (0, 3):
        client.post(
            "/api/v1/quiz-attempts",
            json={"topic_id": topic["id"], "answers": [{"question_id": seeded_questions[0], "selected_index": selected}]},
            headers=student_headers,
        )
    d = client.get("/api/v1/me/dashboard", headers=student_headers).json()
    assert d["attempts"] == 2
    assert d["avg_percent"] == 50.0 and d["best_percent"] == 100.0
    assert d["topics_practiced"] == 1 and d["topics"][0]["attempts"] == 2
    assert d["questions_answered"] == 2 and d["correct_answers"] == 1


def test_admin_question_bank_and_overview(client, admin_headers, student_headers, topic, seeded_questions):
    bank = client.get(f"/api/v1/topics/{topic['id']}/questions?limit=2", headers=admin_headers).json()
    assert bank["total"] == 6 and len(bank["items"]) == 2 and "correct_index" in bank["items"][0]
    assert client.get(f"/api/v1/topics/{topic['id']}/questions", headers=student_headers).status_code == 403

    qid = seeded_questions[0]
    assert client.delete(f"/api/v1/topics/{topic['id']}/questions/{qid}", headers=admin_headers).status_code == 204

    ov = client.get("/api/v1/admin/overview", headers=admin_headers).json()
    assert ov["questions"] == 5 and ov["users"] == 2 and ov["questions_by_source"] == {"ollama": 5}

    detail = client.get(f"/api/v1/topics/{topic['id']}", headers=student_headers).json()
    assert detail["question_count"] == 5 and detail["course_name"] == "Biology"


def test_order_fresh_first_prefers_unseen_then_least_recent():
    from types import SimpleNamespace

    from app.services.attempt_service import order_fresh_first

    pool = [SimpleNamespace(id=i) for i in range(1, 7)]
    seen = {1: 300.0, 2: 100.0, 3: 200.0}  # 2 seen longest ago, 1 most recently
    ordered = [q.id for q in order_fresh_first(pool, seen)]
    assert set(ordered[:3]) == {4, 5, 6}
    assert ordered[3:] == [2, 3, 1]


def test_practice_tops_up_instantly_when_unseen_runs_out(client, student_headers, topic, seeded_questions, monkeypatch):
    import json

    from app.config import settings
    from app.services import generation_service, quiz_service

    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    calls = []

    def fake_generate(prompt, providers=None):
        calls.append(providers)
        texts = ["Which enzyme makes ATP in the inner membrane?", "What is the matrix of the organelle?",
                 "Where are cristae found?", "Which gas is the final electron acceptor?",
                 "How many ATP does glycolysis net per glucose?"]
        qs = [{"question": t, "options": ["a", "b", "c", "d"], "correct_index": 0, "explanation": "x",
               "difficulty": "easy"} for t in texts]
        return {"raw": json.dumps({"questions": qs}), "source": "groq", "model": "m"}

    monkeypatch.setattr(generation_service, "generate", fake_generate)
    monkeypatch.setattr(quiz_service, "retrieve_context",
                        lambda topic_id, query, **kw: [{"text": "notes", "page_number": None, "source_type": "upload", "score": 1}])

    first = client.get(f"/api/v1/topics/{topic['id']}/quiz?count=6", headers=student_headers).json()
    assert first["fresh_generated"] == 0 and first["repeats"] == 0  # 6 unseen questions were enough
    client.post("/api/v1/quiz-attempts", headers=student_headers, json={
        "topic_id": topic["id"], "answers": [{"question_id": q["id"], "selected_index": 0} for q in first["questions"]]})

    second = client.get(f"/api/v1/topics/{topic['id']}/quiz?count=6", headers=student_headers).json()
    assert calls and calls[0] == ("groq", "gemini")  # instant generation uses the fast cloud models only
    assert second["fresh_generated"] == 5
    assert second["repeats"] == 1  # 5 fresh + 1 least-recently-seen
