from app.auth import limiter
from app.db import db

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "redis": True}


def test_register_logs_you_in(client, make_user):
    user = make_user()
    assert user["username"] == "alice"
    assert "token" in client.cookies
    r = client.get(ME)
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"


def test_duplicate_username_or_email_rejected(client, make_user):
    make_user("alice")
    same_name = client.post(
        REGISTER, json={"username": "alice", "email": "other@example.com", "password": "password123"}
    )
    same_email = client.post(
        REGISTER, json={"username": "bob", "email": "alice@example.com", "password": "password123"}
    )
    assert same_name.status_code == 409
    assert same_email.status_code == 409


def test_register_validation(client):
    bad_pw = client.post(
        REGISTER, json={"username": "alice", "email": "a@example.com", "password": "short"}
    )
    bad_name = client.post(
        REGISTER, json={"username": "a b!", "email": "a@example.com", "password": "password123"}
    )
    bad_email = client.post(
        REGISTER, json={"username": "alice", "email": "not-an-email", "password": "password123"}
    )
    assert bad_pw.status_code == 422
    assert bad_name.status_code == 422
    assert bad_email.status_code == 422


def test_password_is_hashed_in_db(make_user):
    make_user(password="password123")
    with db() as conn:
        row = conn.execute("SELECT password_hash FROM users").fetchone()
    assert row["password_hash"] != "password123"
    assert row["password_hash"].startswith("$2")


def test_login_works(make_user, new_client):
    make_user()
    c2 = new_client()
    r = c2.post(LOGIN, json={"email": "alice@example.com", "password": "password123"})
    assert r.status_code == 200
    assert "password_hash" not in r.json()
    assert c2.get(ME).json()["username"] == "alice"


def test_wrong_password_and_unknown_email_get_401(client, make_user):
    make_user()
    wrong = client.post(LOGIN, json={"email": "alice@example.com", "password": "nope-nope"})
    unknown = client.post(LOGIN, json={"email": "ghost@example.com", "password": "password123"})
    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json() == unknown.json()  # no hint about which one was wrong


def test_me_requires_cookie(client):
    assert client.get(ME).status_code == 401


def test_garbage_token_is_rejected(client):
    client.cookies.set("token", "garbage")
    assert client.get(ME).status_code == 401


def test_logout_clears_session(client, make_user):
    make_user()
    assert client.get(ME).status_code == 200
    assert client.post(LOGOUT).status_code == 200
    assert client.get(ME).status_code == 401


def test_login_is_rate_limited(client, make_user):
    make_user()
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [
            client.post(LOGIN, json={"email": "alice@example.com", "password": "wrong-pass"}).status_code
            for _ in range(6)
        ]
    finally:
        limiter.enabled = False
    assert codes[:5] == [401] * 5
    assert codes[5] == 429