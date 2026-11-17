import json

import pytest

from app.services import generation_service, quiz_service
from app.services.dedup_service import filter_duplicates, is_duplicate, question_hash
from app.services.generation_service import build_prompt, parse_questions
from app.services.ingestion_service import chunk_text


def _raw(questions):
    return json.dumps(
        {
            "questions": [
                {"question": q, "options": ["w", "x", "y", "z"], "correct_index": i % 4, "explanation": "e"}
                for i, q in enumerate(questions)
            ]
        }
    )


# --------------------------------------------------------------------------- parsing
def test_parse_handles_fences_think_and_trailing_commas():
    raw = (
        "<think>reasoning</think>```json\n"
        '{"questions": [{"question": "What is ATP?", "options": ["A) a", "B) b", "C) c", "D) d"],'
        ' "answer": "B", "explanation": "x",},]}\n```'
    )
    [q] = parse_questions(raw)
    assert q["options"] == ["a", "b", "c", "d"]
    assert q["correct_index"] == 1


def test_parse_salvages_truncated_output():
    raw = '{"questions": [{"question": "Q1?", "options": ["a","b","c","d"], "correct_index": 0}, {"question": "Q2'
    assert [q["question"] for q in parse_questions(raw)] == ["Q1?"]


def test_mixed_generation_keeps_model_levels(monkeypatch, client, admin_headers, topic):
    raw = json.dumps({"questions": [
        {"question": q, "options": ["w", "x", "y", "z"], "correct_index": 1, "explanation": "e", "difficulty": lvl}
        for q, lvl in [("Where is ATP synthesised?", "easy"), ("Why does cyanide stop oxidative phosphorylation?", "hard"),
                       ("Which membrane holds the electron transport chain?", "medium"), ("Name the Krebs cycle input.", "bogus")]]})
    monkeypatch.setattr(generation_service, "generate", lambda prompt: {"raw": raw, "source": "groq", "model": "m"})
    monkeypatch.setattr(quiz_service, "retrieve_context",
                        lambda topic_id, query, **kw: [{"text": "ATP.", "page_number": 1, "source_type": "upload", "score": 1}])
    r = client.post(f"/api/v1/topics/{topic['id']}/generate-questions", json={"count": 4, "difficulty": "mixed"},
                    headers=admin_headers)
    assert r.status_code == 200, r.text
    assert [q["difficulty"] for q in r.json()["questions"]] == ["easy", "hard", "medium", "medium"]


def test_parse_rejects_invalid_items():
    raw = json.dumps(
        [
            {"question": "three options", "options": ["a", "b", "c"], "correct_index": 0},
            {"question": "bad index", "options": ["a", "b", "c", "d"], "correct_index": 9},
            {"question": "ok", "options": ["a", "b", "c", "d"], "correct_index": "d"},
        ]
    )
    assert [q["question"] for q in parse_questions(raw)] == ["ok"]


def test_prompt_stays_within_budget():
    prompt = build_prompt("Cells", ["word " * 2000] * 10, ["prior question?"] * 50, 10, "hard")
    assert len(prompt) < generation_service.MAX_PROMPT_CHARS + 1500
    assert "HARD" in prompt and "prior question" in prompt


def test_dedup():
    assert is_duplicate("What is the powerhouse of the cell?", ["what is the powerhouse of the cell"])
    kept = filter_duplicates([{"question": "Alpha beta?"}, {"question": "alpha beta"}, {"question": "Gamma?"}], [])
    assert [k["question"] for k in kept] == ["Alpha beta?", "Gamma?"]
    assert question_hash("Hello, World!") == question_hash("hello world")


def test_chunking_overlap_and_no_redundant_tail():
    words = " ".join(f"w{i}" for i in range(400))
    chunks = chunk_text([{"text": words, "page_number": 3}], chunk_size_words=300, overlap_words=50)
    assert len(chunks) == 2
    assert chunks[1]["text"].startswith("w250")
    assert all(c["page_number"] == 3 for c in chunks)
    short = chunk_text([{"text": "a b c", "page_number": 1}], chunk_size_words=300, overlap_words=50)
    assert len(short) == 1


# --------------------------------------------------------------------------- provider fallback
def test_cloud_first_then_local_on_rate_limit(monkeypatch):
    """Groq is rate-limited (long cooldown), Gemini errors (short cooldown), Ollama answers."""
    monkeypatch.setattr(generation_service, "_is_configured", lambda p: True)
    monkeypatch.setattr(generation_service, "_in_cooldown", lambda p: False)
    cooled = {}
    monkeypatch.setattr(generation_service, "_set_cooldown", lambda p, seconds=None: cooled.__setitem__(p, seconds))

    class RateLimitError(Exception):
        status_code = 429

    def groq(prompt):
        raise RateLimitError("Rate limit reached: tokens per day (TPD)")

    def gemini(prompt):
        raise TimeoutError("slow")

    monkeypatch.setitem(generation_service._PROVIDER_CALLS, "groq", groq)
    monkeypatch.setitem(generation_service._PROVIDER_CALLS, "gemini", gemini)
    monkeypatch.setitem(generation_service._PROVIDER_CALLS, "ollama", lambda p: ("{}", "mistral:7b"))
    out = generation_service.generate("prompt")
    assert out["source"] == "ollama"
    assert cooled["groq"] >= 900  # rate limit -> long cooldown
    assert cooled["gemini"] is None  # ordinary failure -> default cooldown


def test_skips_providers_in_cooldown(monkeypatch):
    monkeypatch.setattr(generation_service, "_is_configured", lambda p: True)
    monkeypatch.setattr(generation_service, "_in_cooldown", lambda p: p == "groq")
    monkeypatch.setitem(generation_service._PROVIDER_CALLS, "groq", lambda p: (_ for _ in ()).throw(AssertionError("called")))
    monkeypatch.setitem(generation_service._PROVIDER_CALLS, "gemini", lambda p: ("{}", "gemini-flash-latest"))
    assert generation_service.generate("prompt")["source"] == "gemini"


def test_rate_limit_detection():
    class Quota(Exception):
        pass

    assert generation_service._rate_limit_seconds(Quota("429 You exceeded your current quota")) >= 900

    class RateLimitError(Exception):
        status_code = 429

    tpm = RateLimitError("Rate limit reached on tokens per minute (TPM). Please try again in 15.31s.")
    assert generation_service._rate_limit_seconds(tpm) == 18  # honour the provider's hint, not 15 minutes
    assert generation_service._rate_limit_seconds(RateLimitError("Rate limit reached")) == 15
    groq_tpm = RateLimitError("Rate limit reached for model on tokens per minute (TPM): Limit 8000. Please try again "
                              "in 24.99s. Need more tokens? Upgrade at https://console.groq.com/settings/billing")
    assert generation_service._rate_limit_seconds(groq_tpm) == 27  # per-minute, despite the billing link
    groq_tpd = RateLimitError("Rate limit reached on tokens per day (TPD): Limit 200000. Please try again in 7m.")
    assert generation_service._rate_limit_seconds(groq_tpd) >= 900
    assert generation_service._rate_limit_seconds(ValueError("bad json")) is None


def test_prompt_includes_exam_and_syllabus():
    prompt = build_prompt("OSI model", ["The OSI model has 7 layers."], [], 3, "medium",
                          exam_name="NRB Computer Officer", syllabus_scope="layers, functions, PDUs")
    assert "NRB Computer Officer" in prompt and "layers, functions, PDUs" in prompt


def test_all_providers_fail(monkeypatch):
    monkeypatch.setattr(generation_service, "_is_configured", lambda p: p == "ollama")
    monkeypatch.setattr(generation_service, "_in_cooldown", lambda p: False)
    monkeypatch.setattr(generation_service, "_set_cooldown", lambda p, seconds=None: None)
    monkeypatch.setitem(generation_service._PROVIDER_CALLS, "ollama", lambda p: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(generation_service.GenerationError):
        generation_service.generate("prompt")


# --------------------------------------------------------------------------- end-to-end endpoint
@pytest.fixture()
def fake_llm(monkeypatch):
    batches = []

    def fake_generate(prompt):
        return {"raw": _raw(batches.pop(0)), "source": "ollama", "model": "mistral:7b"}

    monkeypatch.setattr(generation_service, "generate", fake_generate)
    monkeypatch.setattr(
        quiz_service,
        "retrieve_context",
        lambda topic_id, query, **kw: [{"text": "Mitochondria make ATP.", "page_number": 1, "source_type": "upload", "score": 0.9}],
    )
    return batches


def test_generate_endpoint_stores_and_dedups(client, admin_headers, student_headers, topic, fake_llm):
    assert client.post(f"/api/v1/topics/{topic['id']}/generate-questions", json={"count": 1},
                       headers=student_headers).status_code == 403
    fake_llm.append(["What do mitochondria produce?", "Where is the Krebs cycle located?"])
    r = client.post(
        f"/api/v1/topics/{topic['id']}/generate-questions",
        json={"count": 2, "difficulty": "easy"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated"] == 2 and body["context_source"] == "notes"
    assert body["questions"][0]["difficulty"] == "easy"

    # Second run repeats one old question: it must be dropped. Two attempts are
    # made because the first only yields one new question.
    fake_llm.extend([["What do mitochondria produce", "Which membrane folds into cristae?"], ["What is ATP synthase?"]])
    r = client.post(f"/api/v1/topics/{topic['id']}/generate-questions", json={"count": 2}, headers=admin_headers)
    texts = [q["question_text"] for q in r.json()["questions"]]
    assert "What do mitochondria produce" not in texts
    assert "Which membrane folds into cristae?" in texts

    quiz = client.get(f"/api/v1/topics/{topic['id']}/quiz?count=10", headers=student_headers).json()
    assert quiz["available"] == 4


def test_generate_without_content_returns_422(client, admin_headers, topic, monkeypatch):
    monkeypatch.setattr(quiz_service, "retrieve_context", lambda topic_id, query, **kw: [])
    r = client.post(
        f"/api/v1/topics/{topic['id']}/generate-questions",
        json={"count": 2, "use_web_fallback": False},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_generate_async_queues_task(client, admin_headers, topic, monkeypatch):
    from app.workers import generation_worker

    calls = {}

    class FakeTask:
        id = "task-123"

    def fake_delay(**kwargs):
        calls.update(kwargs)
        return FakeTask()

    monkeypatch.setattr(generation_worker.generate_questions_task, "delay", fake_delay)
    r = client.post(
        f"/api/v1/topics/{topic['id']}/generate-questions",
        json={"count": 5, "run_async": True, "use_web_fallback": False},
        headers=admin_headers,
    )
    assert r.status_code == 202 and r.json()["task_id"] == "task-123"
    assert calls["allow_web_fallback"] is False


def test_patient_mode_waits_for_a_provider(monkeypatch):
    calls = {"n": 0}

    def once(prompt, providers=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise generation_service.GenerationError("All LLM providers failed: groq: in cooldown")
        return {"raw": "{}", "source": "groq", "model": "m"}

    monkeypatch.setattr(generation_service, "_generate_once", once)
    monkeypatch.setattr(generation_service, "_is_configured", lambda p: p == "groq")
    monkeypatch.setattr(generation_service, "_cooldown_left", lambda p: 0.0)
    monkeypatch.setattr(generation_service.time, "sleep", lambda s: None)
    with pytest.raises(generation_service.GenerationError):
        generation_service.generate("p")  # interactive: fails fast
    calls["n"] = 0
    with generation_service.patient(30):
        assert generation_service.generate("p")["source"] == "groq"  # background: waits and retries
    assert calls["n"] == 2
