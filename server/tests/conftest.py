import os
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values

_ROOT = Path(__file__).resolve().parents[2]
_env = dotenv_values(_ROOT / ".env")
_dev_url = _env["DATABASE_URL"]
_test_url = _dev_url.rsplit("/", 1)[0] + "/microblog_test"
os.environ["DATABASE_URL"] = _test_url
os.environ["REDIS_URL"] = _env["REDIS_URL"].rsplit("/", 1)[0] + "/15"


def _ensure_test_db() -> None:
    with psycopg.connect(_dev_url, autocommit=True) as c:
        exists = c.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'microblog_test'"
        ).fetchone()
        if not exists:
            c.execute("CREATE DATABASE microblog_test")
    with psycopg.connect(_test_url) as c:
        has_tables = c.execute("SELECT to_regclass('public.users')").fetchone()[0]
        if not has_tables:
            c.execute((Path(__file__).resolve().parents[1] / "schema.sql").read_text())


_ensure_test_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import limiter  # noqa: E402
from app.db import db, rds  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(client):
    limiter.enabled = False
    with db() as conn:
        conn.execute(
            "TRUNCATE users, posts, follows, hashtags, likes RESTART IDENTITY CASCADE"
        )
    rds.flushdb()
    client.cookies.clear()
    yield


@pytest.fixture
def new_client():
    return lambda: TestClient(app)


@pytest.fixture
def make_user(client):

    def _make(name="alice", password="password123"):
        r = client.post(
            "/api/v1/auth/register",
            json={"username": name, "email": f"{name}@example.com", "password": password},
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _make