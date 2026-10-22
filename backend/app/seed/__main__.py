"""python -m app.seed [--if-empty | --reset]  — seeds Northstar Analytics and Lumen Ledger.

--if-empty  seed each demo workspace that does not exist yet (used on container start)
--reset     wipe and reload both demo workspaces (reviewer-created workspaces are untouched)
"""
import sys

from sqlalchemy import select

from ..db import session_scope
from ..models import Workspace
from .load import SEEDS, reset_workspace


def main(argv: list[str]) -> None:
    for slug, (name, seed) in SEEDS.items():
        with session_scope() as db:
            exists = db.scalar(select(Workspace).where(Workspace.slug == slug)) is not None
            if exists and "--if-empty" in argv:
                print(f"seed: {name} already present; skipping")
                continue
            if exists and "--reset" not in argv:
                print(f"seed: {name} exists; use --reset to wipe and reload it")
                continue
            if exists:
                reset_workspace(db, slug)
            seed(db)
        print(f"seed: {name} loaded")


main(sys.argv[1:])
