"""python -m app.seed [--if-empty | --reset]"""
import sys

from sqlalchemy import select

from ..db import session_scope
from ..models import Workspace
from .load import reset_workspace, seed_northstar
from .northstar import WORKSPACE


def main(argv: list[str]) -> None:
    with session_scope() as db:
        exists = db.scalar(select(Workspace).where(Workspace.slug == WORKSPACE["slug"])) is not None
        if exists and "--if-empty" in argv:
            print("seed: Northstar Analytics already present; skipping")
            return
        if exists and "--reset" not in argv:
            print("seed: workspace exists; use --reset to wipe and reload it")
            return
        if exists:
            reset_workspace(db, WORKSPACE["slug"])
        seed_northstar(db)
    print("seed: Northstar Analytics loaded")


main(sys.argv[1:])
