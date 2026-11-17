import io

import pytest

from app.workers import ingestion_worker


class FakeTask:
    id = "ingest-1"


@pytest.fixture()
def queued(monkeypatch):
    calls = []

    def fake_delay(**kwargs):
        calls.append(kwargs)
        return FakeTask()

    monkeypatch.setattr(ingestion_worker.ingest_pdf_task, "delay", fake_delay)
    return calls


def test_rejects_non_pdf(client, admin_headers, topic, queued):
    r = client.post(
        f"/api/v1/topics/{topic['id']}/upload-syllabus",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=admin_headers,
    )
    assert r.status_code == 400
    fake = client.post(
        f"/api/v1/topics/{topic['id']}/upload-syllabus",
        files={"file": ("notes.pdf", b"not really a pdf", "application/pdf")},
        headers=admin_headers,
    )
    assert fake.status_code == 400
    assert queued == []


def test_students_cannot_upload(client, student_headers, topic, queued):
    r = client.post(
        f"/api/v1/topics/{topic['id']}/upload-syllabus",
        files={"file": ("a.pdf", b"%PDF-1.4 data", "application/pdf")},
        headers=student_headers,
    )
    assert r.status_code == 403


def test_upload_queues_ingestion_and_deletes(client, admin_headers, topic, queued):
    for _ in range(2):  # same name twice must not overwrite
        r = client.post(
            f"/api/v1/topics/{topic['id']}/upload-syllabus",
            files={"file": ("../evil/notes.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
            headers=admin_headers,
        )
        assert r.status_code == 202, r.text
    doc = r.json()["document"]
    assert doc["status"] == "pending" and doc["filename"] == ".._evil_notes.pdf" and doc["task_id"] == "ingest-1"
    paths = {c["file_path"] for c in queued}
    assert len(paths) == 2 and all("/evil/" not in p for p in paths)

    status = client.get(f"/api/v1/topics/{topic['id']}/status", headers=admin_headers).json()
    assert status["processing"] is True and len(status["documents"]) == 2

    r = client.delete(f"/api/v1/topics/{topic['id']}/documents/{doc['id']}", headers=admin_headers)
    assert r.status_code == 204
    status = client.get(f"/api/v1/topics/{topic['id']}/status", headers=admin_headers).json()
    assert len(status["documents"]) == 1


def test_upload_size_limit(client, admin_headers, topic, queued, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    big = b"%PDF-" + b"0" * (2 * 1024 * 1024)
    r = client.post(
        f"/api/v1/topics/{topic['id']}/upload-syllabus",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers=admin_headers,
    )
    assert r.status_code == 413


def test_ingestion_task_marks_ready(db_session_factory, topic, monkeypatch, tmp_path):
    from app.models import SyllabusDocument, Topic

    session = db_session_factory()
    doc = SyllabusDocument(topic_id=topic["id"], filename="n.pdf", stored_filename="x.pdf", status="pending")
    session.add(doc)
    session.commit()
    doc_id = doc.id
    session.close()

    monkeypatch.setattr(ingestion_worker, "SessionLocal", db_session_factory)
    monkeypatch.setattr(
        ingestion_worker,
        "extract_and_chunk",
        lambda path: [{"text": "chunk one", "page_number": 1}, {"text": "chunk two", "page_number": 2}],
    )
    monkeypatch.setattr(ingestion_worker, "count_pages", lambda path: 2)
    monkeypatch.setattr(ingestion_worker, "embed_batch", lambda texts: [[0.0] * 384 for _ in texts])
    monkeypatch.setattr(ingestion_worker, "delete_points", lambda *a, **k: None)
    stored = {}
    monkeypatch.setattr(ingestion_worker, "upsert_chunks", lambda **kw: stored.update(kw) or len(kw["texts"]))

    result = ingestion_worker.ingest_pdf_task.apply(
        kwargs=dict(topic_id=topic["id"], chapter_id=topic["chapter_id"], file_path="x.pdf", syllabus_document_id=doc_id)
    ).get()
    assert result["status"] == "ready" and stored["document_id"] == doc_id

    session = db_session_factory()
    assert session.get(SyllabusDocument, doc_id).chunk_count == 2
    assert session.get(Topic, topic["id"]).has_content is True
    session.close()


def test_ingestion_missing_file_fails_permanently(db_session_factory, topic, monkeypatch):
    from app.models import SyllabusDocument

    session = db_session_factory()
    doc = SyllabusDocument(topic_id=topic["id"], filename="n.pdf", status="pending")
    session.add(doc)
    session.commit()
    doc_id = doc.id
    session.close()

    monkeypatch.setattr(ingestion_worker, "SessionLocal", db_session_factory)
    res = ingestion_worker.ingest_pdf_task.apply(
        kwargs=dict(topic_id=topic["id"], chapter_id=1, file_path="/nope/missing.pdf", syllabus_document_id=doc_id)
    )
    assert res.failed()
    session = db_session_factory()
    d = session.get(SyllabusDocument, doc_id)
    assert d.status == "failed" and "missing" in d.error
    session.close()
