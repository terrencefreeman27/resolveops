"""Tests run inside the api container against a real Postgres database (resolveops_test)."""
import os

import psycopg
import pytest

_base = os.environ.get("DATABASE_URL", "postgresql+psycopg://resolveops:resolveops@db:5432/resolveops")
_root, _ = _base.rsplit("/", 1)
TEST_URL = f"{_root}/resolveops_test"
os.environ["DATABASE_URL"] = TEST_URL
os.environ["AI_MODE"] = "demo"


def _recreate_db() -> None:
    admin = _base.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS resolveops_test WITH (FORCE)")
        conn.execute("CREATE DATABASE resolveops_test")


_recreate_db()

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.adapters.internal import FAULTS  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.load import seed_northstar  # noqa: E402

HDR = {"X-ResolveOps": "1"}
WS = "/api/w/northstar"


@pytest.fixture(scope="session", autouse=True)
def database():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        seed_northstar(db)
        db.commit()
    yield


@pytest.fixture(autouse=True)
def reset_faults():
    FAULTS.update(fail_next=0, fail_after_write=0)
    yield
    FAULTS.update(fail_next=0, fail_after_write=0)


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def new_visitor() -> TestClient:
    c = TestClient(app, headers=HDR)
    assert c.post("/api/demo/session").status_code == 200
    return c


def new_reviewer() -> TestClient:
    c = TestClient(app, headers=HDR)
    r = c.post("/api/auth/login", json={"email": "reviewer@northstar.example", "password": "northstar-demo"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def visitor() -> TestClient:
    return new_visitor()


@pytest.fixture
def reviewer() -> TestClient:
    return new_reviewer()


def run_scenario(client: TestClient, key: str) -> dict:
    r = client.post(f"{WS}/scenarios/{key}/run")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "awaiting_review", d["state_reason"]
    return d


def approve_body(detail: dict) -> dict:
    v = detail["proposal"]["version"]
    return {"proposal_version_id": v["id"], "action_hash": v["action_hash"]}
