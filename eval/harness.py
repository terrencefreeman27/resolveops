"""Shared setup for the evaluation suites. Runs inside the api container (eval/ is mounted at /srv/eval).

The suites never touch the demo database: they recreate a dedicated `resolveops_eval` database, run
the migrations and seed both demo workspaces into it. DATABASE_URL must be switched *before* any
`app` module is imported, so call `prepare_database()` first and import app code afterwards.
"""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
DATASET_DIR = EVAL_DIR / "datasets"
HDR = {"X-ResolveOps": "1"}

_base = os.environ.get("DATABASE_URL", "postgresql+psycopg://resolveops:resolveops@db:5432/resolveops")
_root, _ = _base.rsplit("/", 1)
EVAL_DB_URL = f"{_root}/resolveops_eval"


def prepare_database(ai_mode: str = "demo") -> None:
    """Drop and recreate resolveops_eval, migrate, seed. Must run before importing `app`."""
    import psycopg

    admin = _base.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS resolveops_eval WITH (FORCE)")
        conn.execute("CREATE DATABASE resolveops_eval")
    os.environ["DATABASE_URL"] = EVAL_DB_URL
    os.environ["AI_MODE"] = ai_mode
    os.environ["SEED_ON_START"] = "false"

    from alembic import command
    from alembic.config import Config

    backend = Path("/srv")
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = EVAL_DB_URL
    command.upgrade(cfg, "head")

    from app.db import SessionLocal
    from app.seed.load import seed_all

    with SessionLocal() as db:
        seed_all(db)
        db.commit()


def git_commit() -> str:
    """The repo is not mounted into the container, so the caller may pass EVAL_GIT_COMMIT."""
    if os.environ.get("EVAL_GIT_COMMIT"):
        return os.environ["EVAL_GIT_COMMIT"]
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=EVAL_DIR, check=True).stdout.strip()
    except Exception:
        return "unknown (set EVAL_GIT_COMMIT=$(git rev-parse --short HEAD))"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_result(suite: str, mode: str, payload: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{suite}-{mode}-{today()}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def load_cases(version: str = "v1") -> list[dict]:
    path = DATASET_DIR / version / "cases.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
