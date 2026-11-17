def test_first_user_is_admin_second_is_not(client):
    first = client.post("/api/v1/auth/register", json={"email": "A@Example.com ", "password": "secret123"})
    assert first.status_code == 201
    assert first.json()["user"]["is_admin"] is True
    assert first.json()["user"]["email"] == "a@example.com"

    second = client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "secret123"})
    assert second.json()["user"]["is_admin"] is False


def test_duplicate_email_conflict(client):
    client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "secret123"})
    r = client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "secret123"})
    assert r.status_code == 409


def test_login_and_me(client):
    client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "secret123", "full_name": "Ann"})
    bad = client.post("/api/v1/auth/login", data={"username": "a@example.com", "password": "nope"})
    assert bad.status_code == 401

    ok = client.post("/api/v1/auth/login", data={"username": "A@example.com", "password": "secret123"})
    assert ok.status_code == 200
    headers = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["full_name"] == "Ann"


def test_protected_routes_need_token(client):
    assert client.get("/api/v1/courses").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_change_password(client, admin_headers):
    wrong = client.patch(
        "/api/v1/auth/me", json={"current_password": "x", "new_password": "newpass1"}, headers=admin_headers
    )
    assert wrong.status_code == 400
    ok = client.patch(
        "/api/v1/auth/me",
        json={"current_password": "secret123", "new_password": "newpass1", "full_name": "Boss"},
        headers=admin_headers,
    )
    assert ok.status_code == 200 and ok.json()["full_name"] == "Boss"
    assert client.post("/api/v1/auth/login", data={"username": "admin@example.com", "password": "newpass1"}).status_code == 200


def test_disabled_user_cannot_login(client, admin_headers, student_headers):
    users = client.get("/api/v1/admin/users", headers=admin_headers).json()
    student = next(u for u in users if u["email"] == "student@example.com")
    client.patch(f"/api/v1/admin/users/{student['id']}", json={"is_active": False}, headers=admin_headers)
    r = client.post("/api/v1/auth/login", data={"username": "student@example.com", "password": "secret123"})
    assert r.status_code == 403
    assert client.get("/api/v1/auth/me", headers=student_headers).status_code == 401


def test_admin_cannot_demote_self(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    r = client.patch(f"/api/v1/admin/users/{me['id']}", json={"is_admin": False}, headers=admin_headers)
    assert r.status_code == 400
