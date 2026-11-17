"""Test fixtures: in-memory SQLite, no network (Qdrant/Redis/LLMs/Celery are stubbed)."""

import os
import sys
from pathlib import Path

# Must be set before any app module is imported (Settings reads env at import).
os.environ.update(
    DATABASE_URL="sqlite://",
    QDRANT_URL="http://qdrant.invalid:6333",
    QDRANT_API_KEY="",
    REDIS_URL="redis://127.0.0.1:1/0",
    REDIS_LOCAL_URL="",
    QDRANT_LOCAL_URL="",
    OLLAMA_BASE_URL="http://127.0.0.1:1",
    GROQ_API_KEY="",
    GEMINI_API_KEY="",
    JWT_SECRET="test-secret-key-that-is-long-enough-for-hs256",
    ADMIN_EMAILS="",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def db_session_factory(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    from app.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    # Never touch Qdrant from tests.
    monkeypatch.setattr("app.utils.cleanup.delete_points", lambda *a, **k: None)
    monkeypatch.setattr("app.routers.topics.topic_chunk_count", lambda *a, **k: 0)
    # No network in tests: web research returns nothing.
    monkeypatch.setattr("app.services.quiz_service.search_topic_context", lambda *a, **k: [])
    monkeypatch.setattr("app.workers.research_worker.search_topic_context", lambda *a, **k: [])
    # No background queue in tests.
    monkeypatch.setattr("app.workers.research_worker.queue_top_up", lambda *a, **k: False)
    yield factory
    engine.dispose()


@pytest.fixture()
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture()
def client(db_session_factory):
    def override():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email, password="secret123", name=None):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": name})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def admin_headers(client):
    token = _register(client, "admin@example.com", name="Admin")["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def student_headers(client, admin_headers):
    token = _register(client, "student@example.com", name="Student")["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def topic(client, admin_headers):
    """A published course → chapter → topic, returned as the topic JSON."""
    course = client.post("/api/v1/courses", json={"name": "Biology"}, headers=admin_headers).json()
    chapter = client.post("/api/v1/chapters", json={"course_id": course["id"], "name": "Cells"}, headers=admin_headers).json()
    t = client.post("/api/v1/topics", json={"chapter_id": chapter["id"], "name": "Mitochondria"}, headers=admin_headers)
    assert t.status_code == 201, t.text
    return t.json()


@pytest.fixture()
def seeded_questions(db, topic):
    from app.models import GeneratedQuestion
    from app.services.dedup_service import question_hash

    rows = []
    for i in range(6):
        text = f"Question number {i} about mitochondria energy production stage {i * 7}?"
        rows.append(
            GeneratedQuestion(
                topic_id=topic["id"],
                question_text=text,
                options=["A", "B", "C", "D"],
                correct_index=i % 4,
                explanation=f"Because {i}",
                source="ollama",
                difficulty="easy" if i < 3 else "hard",
                question_hash=question_hash(text),
            )
        )
    db.add_all(rows)
    db.commit()
    return [r.id for r in rows]
