def test_course_tree_crud(client, admin_headers):
    course = client.post("/api/v1/courses", json={"name": "Physics", "description": "Intro"}, headers=admin_headers).json()
    ch2 = client.post("/api/v1/chapters", json={"course_id": course["id"], "name": "Waves", "order": 5}, headers=admin_headers).json()
    ch1 = client.post("/api/v1/chapters", json={"course_id": course["id"], "name": "Motion", "order": 1}, headers=admin_headers).json()
    ch3 = client.post("/api/v1/chapters", json={"course_id": course["id"], "name": "Heat"}, headers=admin_headers).json()
    assert ch3["order"] == 6  # appended after the current max

    client.post("/api/v1/topics", json={"chapter_id": ch1["id"], "name": "Velocity"}, headers=admin_headers)
    client.post("/api/v1/topics", json={"chapter_id": ch1["id"], "name": "Acceleration"}, headers=admin_headers)

    tree = client.get(f"/api/v1/courses/{course['id']}", headers=admin_headers).json()
    assert [c["name"] for c in tree["chapters"]] == ["Motion", "Waves", "Heat"]
    assert [t["name"] for t in tree["chapters"][0]["topics"]] == ["Velocity", "Acceleration"]

    listing = client.get("/api/v1/courses", headers=admin_headers).json()
    assert listing[0]["chapter_count"] == 3 and listing[0]["topic_count"] == 2

    r = client.patch(f"/api/v1/chapters/{ch2['id']}", json={"name": "Sound"}, headers=admin_headers)
    assert r.json()["name"] == "Sound"

    assert client.delete(f"/api/v1/chapters/{ch1['id']}", headers=admin_headers).status_code == 204
    tree = client.get(f"/api/v1/courses/{course['id']}", headers=admin_headers).json()
    assert len(tree["chapters"]) == 2

    assert client.delete(f"/api/v1/courses/{course['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/v1/courses/{course['id']}", headers=admin_headers).status_code == 404


def test_students_cannot_modify(client, student_headers):
    assert client.post("/api/v1/courses", json={"name": "X"}, headers=student_headers).status_code == 403


def test_unpublished_courses_hidden_from_students(client, admin_headers, student_headers):
    hidden = client.post("/api/v1/courses", json={"name": "Draft", "is_published": False}, headers=admin_headers).json()
    client.post("/api/v1/courses", json={"name": "Live"}, headers=admin_headers)
    names = [c["name"] for c in client.get("/api/v1/courses", headers=student_headers).json()]
    assert names == ["Live"]
    assert client.get(f"/api/v1/courses/{hidden['id']}", headers=student_headers).status_code == 404
    assert len(client.get("/api/v1/courses", headers=admin_headers).json()) == 2


def test_delete_course_with_attempts(client, admin_headers, student_headers, topic, seeded_questions):
    client.post(
        "/api/v1/quiz-attempts",
        json={"topic_id": topic["id"], "answers": [{"question_id": seeded_questions[0], "selected_index": 0}]},
        headers=student_headers,
    )
    tree_course = client.get(f"/api/v1/topics/{topic['id']}", headers=admin_headers).json()["course_id"]
    assert client.delete(f"/api/v1/courses/{tree_course}", headers=admin_headers).status_code == 204
    assert client.get("/api/v1/quiz-attempts/me", headers=student_headers).json() == []
