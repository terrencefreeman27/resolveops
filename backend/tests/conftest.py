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
from app.seed.load import seed_all  # noqa: E402

HDR = {"X-ResolveOps": "1"}
WS = "/api/w/northstar"


@pytest.fixture(scope="session", autouse=True)
def database():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        seed_all(db)
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


# --- live mode (fake Anthropic client; no network, no real key) -----------------------------

FAKE_KEY = "sk-ant-test-not-a-real-key"


class LiveHarness:
    """Switches the app to AI_MODE=live with a fake Anthropic client for one test."""

    def __init__(self, monkeypatch):
        from app.config import get_settings
        from app.providers import live as live_mod

        self.settings = get_settings()
        self.client = None
        self.factory_calls = 0
        self.mp = monkeypatch
        for k, v in {"ai_mode": "live", "anthropic_api_key": FAKE_KEY, "live_retry_base_delay_s": 0.0,
                     "live_retry_max_delay_s": 0.0, "live_rate_per_reviewer_per_min": 10_000,
                     "live_rate_global_per_min": 10_000, "live_monthly_token_budget": 10**12,
                     "live_max_concurrency": 4}.items():
            monkeypatch.setattr(self.settings, k, v)

        def factory(_settings):
            self.factory_calls += 1
            assert self.client is not None, "test did not install a fake client"
            return self.client
        monkeypatch.setattr(live_mod, "client_factory", factory)

    def set(self, **kw):
        for k, v in kw.items():
            self.mp.setattr(self.settings, k, v)

    def script(self, steps):
        from tests.live_fakes import FakeAnthropic

        self.client = FakeAnthropic(steps)
        return self.client


@pytest.fixture
def live(monkeypatch) -> LiveHarness:
    return LiveHarness(monkeypatch)


def customer_id(client: TestClient, company: str) -> str:
    rows = client.get(f"{WS}/customers").json()["customers"]
    return next(c["id"] for c in rows if c["company_name"] == company)


LUMEN = "/api/w/lumen"


def login(email: str, password: str) -> TestClient:
    c = TestClient(app, headers=HDR)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


def lumen_reviewer() -> TestClient:
    """Member of Lumen Ledger only."""
    return login("reviewer@lumenledger.example", "lumen-demo")


def new_workspace(client: TestClient, name: str | None = None) -> str:
    import uuid as _uuid
    name = name or f"Test Co {_uuid.uuid4().hex[:6]}"
    r = client.post("/api/workspaces", json={"name": name, "ticket_groups": ["Support", "Billing"]})
    assert r.status_code == 200, r.text
    return r.json()["slug"]


def upload(client: TestClient, slug: str, filename: str, content: str, doc_id: str | None = None):
    path = f"/api/w/{slug}/admin/documents" + (f"/{doc_id}/versions" if doc_id else "")
    return client.post(path, json={"filename": filename, "content": content})
