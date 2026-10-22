"""Load the demo workspaces: Northstar Analytics and Lumen Ledger.

Everything company-specific — profile, customers, subscriptions, invoices, documents, escalation rules,
tickets, seeded requests and the simulated-AI fixtures — is written as workspace-scoped rows here.
Application code never branches on which company it is serving.
"""
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..documents import ingest_document
from ..models import (AccountUser, Customer, EscalationRule, Invoice, Membership, Reviewer, SimFixture, Subscription,
                      SupportRequest, Ticket, Workspace)
from ..providers.simulated import normalize
from ..security import hash_password
from . import lumen as L
from . import lumen_fixtures as LF
from . import northstar as N
from . import northstar_fixtures as NF

DOCS_DIR = Path(__file__).parent / "docs"
LUMEN_REVIEWER = ("reviewer@lumenledger.example", "Sam Okoro (Lumen Ledger reviewer)", "lumen-demo")


def _email(name: str, contact_email: str) -> str:
    domain = contact_email.split("@")[1]
    return name.lower().replace(" ", ".") + "@" + domain


def _reviewer(db: Session, email: str, name: str, password: str) -> Reviewer:
    r = db.scalar(select(Reviewer).where(Reviewer.email == email))
    if r is None:
        r = Reviewer(email=email, name=name, password_hash=hash_password(password))
        db.add(r)
        db.flush()
    return r


def _member(db: Session, reviewer: Reviewer, ws: Workspace, role: str = "admin") -> None:
    if db.scalar(select(Membership).where(Membership.reviewer_id == reviewer.id, Membership.workspace_id == ws.id)) is None:
        db.add(Membership(reviewer_id=reviewer.id, workspace_id=ws.id, role=role))


def _workspace(db: Session, data: dict) -> Workspace:
    ws = Workspace(slug=data["slug"], name=data["name"], profile=data["profile"], settings=data["settings"])
    db.add(ws)
    db.flush()
    return ws


def _users(db: Session, ws: Workspace, c: Customer, users, now) -> None:
    for i, (uname, role) in enumerate(users):
        db.add(AccountUser(workspace_id=ws.id, customer_id=c.id, name=uname,
                           email=c.contact_email if uname == c.contact_name else _email(uname, c.contact_email),
                           role=role, last_login_at=now - timedelta(hours=3 + i * 7)))


def _common(db: Session, ws: Workspace, mod, fixtures: dict, by_ref: dict[str, Customer], now) -> None:
    """Rules, tickets, seeded inbox, simulated fixtures and documents."""
    for r in mod.ESCALATION_RULES:
        db.add(EscalationRule(workspace_id=ws.id, **r))
    prefix = ws.settings.get("ticket_prefix", "T")
    for i, (ref, subject, category, priority, status, group, ago, body) in enumerate(mod.TICKETS):
        db.add(Ticket(workspace_id=ws.id, customer_id=by_ref[ref].id, number=f"{prefix}-{901 + i}",
                      subject=subject, body=body, category=category, priority=priority, status=status,
                      group=group, source="seed", created_at=N.days_ago(ago, now), updated_at=N.days_ago(ago, now)))
    db.flush()
    bodies = {}
    for key, ref, subject, body, minutes_ago in mod.REQUESTS:
        c = by_ref[ref]
        bodies[key] = body
        db.add(SupportRequest(workspace_id=ws.id, customer_id=c.id, submitted_via="seed", from_name=c.contact_name,
                              from_email=c.contact_email, subject=subject, body=body, scenario_key=key,
                              is_template=True, state="received", received_at=now - timedelta(minutes=minutes_ago)))
    for key, fx in fixtures.items():
        db.add(SimFixture(workspace_id=ws.id, key=key, match_text=normalize(bodies[key]),
                          classification=fx["classification"], synthesis=fx["synthesis"]))
    for slug, title in mod.DOCS:
        ingest_document(db, ws.id, slug, title, (DOCS_DIR / ws.slug / f"{slug}.md").read_text())
    db.flush()


def seed_northstar(db: Session) -> Workspace:
    now = N.now()
    ws = _workspace(db, N.WORKSPACE)
    s = get_settings()
    _member(db, _reviewer(db, s.seed_reviewer_email, "Riley Morgan (demo reviewer)", s.seed_reviewer_password), ws)

    by_ref: dict[str, Customer] = {}
    for (ref, company, contact, email, plan, status, cycle, bought, used, period_ago, prev_plan, changed_ago,
         users, meta) in N.CUSTOMERS:
        c = Customer(workspace_id=ws.id, account_ref=ref, company_name=company, contact_name=contact,
                     contact_email=email, is_synthetic=True, meta=meta)
        db.add(c)
        db.flush()
        by_ref[ref] = c
        _users(db, ws, c, users, now)
        period_start = N.days_ago(period_ago, now)
        period_len = 365 if cycle == "annual" else 30
        price = N.PLAN_PRICE_CENTS[plan]
        db.add(Subscription(
            workspace_id=ws.id, customer_id=c.id, plan=plan, status=status, billing_cycle=cycle,
            seats_purchased=bought, seats_used=used, price_per_seat_cents=price,
            current_period_start=period_start, current_period_end=period_start + timedelta(days=period_len),
            previous_plan=prev_plan, plan_changed_at=N.days_ago(changed_ago, now) if changed_ago else None,
            features=N.PLAN_FEATURES[plan]))
        # Invoices consistent with Northstar's billing docs: renewal at period start, plus proration / seat add-on.
        year = now.year
        months = 12 if cycle == "annual" else 1
        base_seats = bought - meta.get("seat_change", {}).get("added", 0)
        renewal_price = N.PLAN_PRICE_CENTS[prev_plan] if prev_plan else price
        invoice_no = 10000 + int(ref.split("-")[1])
        db.add(Invoice(workspace_id=ws.id, customer_id=c.id, number=f"INV-{year}-{invoice_no}1", kind="renewal",
                       description=f"{prev_plan or plan} renewal, {base_seats} seats", status="paid" if status != "past_due" else "failed",
                       amount_cents=base_seats * renewal_price * months, issued_at=period_start))
        if prev_plan and changed_ago:
            remaining = period_len - (period_ago - changed_ago)
            diff = price - N.PLAN_PRICE_CENTS[prev_plan]
            db.add(Invoice(workspace_id=ws.id, customer_id=c.id, number=f"INV-{year}-{invoice_no}2", kind="proration",
                           description=f"Upgrade {prev_plan} → {plan}, {bought} seats, prorated {remaining} days",
                           status="paid", amount_cents=round(bought * diff * remaining / period_len),
                           issued_at=N.days_ago(changed_ago, now)))
        if "seat_change" in meta:
            added, ago = meta["seat_change"]["added"], meta["seat_change"]["days_ago"]
            remaining = period_len - (period_ago - ago)
            db.add(Invoice(workspace_id=ws.id, customer_id=c.id, number=f"INV-{year}-{invoice_no}3", kind="seat_addon",
                           description=f"{added} seats added, prorated {remaining} days", status="paid",
                           amount_cents=round(added * price * remaining / period_len), issued_at=N.days_ago(ago, now)))
    _common(db, ws, N, NF.FIXTURES, by_ref, now)
    return ws


def seed_lumen(db: Session) -> Workspace:
    now = N.now()
    ws = _workspace(db, L.WORKSPACE)
    s = get_settings()
    # The Northstar demo reviewer belongs to both demo workspaces (to show the switcher); the Lumen
    # reviewer belongs to Lumen only (to show per-workspace reviewer access).
    riley = _reviewer(db, s.seed_reviewer_email, "Riley Morgan (demo reviewer)", s.seed_reviewer_password)
    _member(db, riley, ws)
    _member(db, _reviewer(db, *LUMEN_REVIEWER), ws)
    by_ref: dict[str, Customer] = {}
    for x in L.CUSTOMERS:
        c = Customer(workspace_id=ws.id, account_ref=x["ref"], company_name=x["company"], contact_name=x["contact"],
                     contact_email=x["email"], is_synthetic=True, meta={})
        db.add(c)
        db.flush()
        by_ref[x["ref"]] = c
        _users(db, ws, c, x["users"], now)
        start = N.days_ago(x["period_days_ago"], now)
        db.add(Subscription(
            workspace_id=ws.id, customer_id=c.id, plan=x["plan"], status=x["status"], billing_cycle=x["cycle"],
            seats_purchased=x["seats"], seats_used=x["used"], price_per_seat_cents=L.PLAN_PRICE_CENTS[x["plan"]],
            current_period_start=start, current_period_end=start + timedelta(days=x["period_len"]),
            previous_plan=x["previous_plan"],
            plan_changed_at=N.days_ago(x["changed_days_ago"], now) if x["changed_days_ago"] else None,
            features=L.PLAN_FEATURES[x["plan"]]))
        for i, (kind, desc, cents, ago, status) in enumerate(x["invoices"]):
            db.add(Invoice(workspace_id=ws.id, customer_id=c.id, number=f"LL-INV-{x['ref'][3:]}-{i + 1}", kind=kind,
                           description=desc, amount_cents=cents, status=status, issued_at=N.days_ago(ago, now)))
    _common(db, ws, L, LF.FIXTURES, by_ref, now)
    return ws


SEEDS = {N.WORKSPACE["slug"]: (N.WORKSPACE["name"], seed_northstar), L.WORKSPACE["slug"]: (L.WORKSPACE["name"], seed_lumen)}


def seed_all(db: Session) -> list[Workspace]:
    return [fn(db) for _name, fn in SEEDS.values()]


def reset_workspace(db: Session, slug: str) -> None:
    db.execute(delete(Workspace).where(Workspace.slug == slug))
    db.flush()
