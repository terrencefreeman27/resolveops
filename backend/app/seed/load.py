"""Load the Northstar Analytics workspace."""
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (AccountUser, Customer, EscalationRule, Invoice, Membership, Reviewer, Subscription,
                      SupportRequest, Ticket, Workspace)
from ..retrieval import ingest_document
from ..security import hash_password
from . import northstar as N

DOCS_DIR = Path(__file__).parent / "docs"


def _email(name: str, contact_email: str) -> str:
    domain = contact_email.split("@")[1]
    return name.lower().replace(" ", ".") + "@" + domain


def seed_northstar(db: Session) -> Workspace:
    now = N.now()
    ws = Workspace(slug=N.WORKSPACE["slug"], name=N.WORKSPACE["name"], profile=N.WORKSPACE["profile"],
                   settings=N.WORKSPACE["settings"])
    db.add(ws)
    db.flush()

    s = get_settings()
    reviewer = db.scalar(select(Reviewer).where(Reviewer.email == s.seed_reviewer_email))
    if reviewer is None:
        reviewer = Reviewer(email=s.seed_reviewer_email, name="Riley Morgan (demo reviewer)",
                            password_hash=hash_password(s.seed_reviewer_password))
        db.add(reviewer)
        db.flush()
    db.add(Membership(reviewer_id=reviewer.id, workspace_id=ws.id, role="admin"))

    by_ref: dict[str, Customer] = {}
    for (ref, company, contact, email, plan, status, cycle, bought, used, period_ago, prev_plan, changed_ago,
         users, meta) in N.CUSTOMERS:
        c = Customer(workspace_id=ws.id, account_ref=ref, company_name=company, contact_name=contact,
                     contact_email=email, is_synthetic=True, meta=meta)
        db.add(c)
        db.flush()
        by_ref[ref] = c
        for i, (uname, role) in enumerate(users):
            db.add(AccountUser(workspace_id=ws.id, customer_id=c.id, name=uname,
                               email=email if uname == contact else _email(uname, email), role=role,
                               last_login_at=now - timedelta(hours=3 + i * 7)))
        period_start = N.days_ago(period_ago, now)
        period_len = 365 if cycle == "annual" else 30
        price = N.PLAN_PRICE_CENTS[plan]
        db.add(Subscription(
            workspace_id=ws.id, customer_id=c.id, plan=plan, status=status, billing_cycle=cycle,
            seats_purchased=bought, seats_used=used, price_per_seat_cents=price,
            current_period_start=period_start, current_period_end=period_start + timedelta(days=period_len),
            previous_plan=prev_plan, plan_changed_at=N.days_ago(changed_ago, now) if changed_ago else None,
            features=N.PLAN_FEATURES[plan]))
        # Invoices consistent with billing docs: renewal at period start, plus proration / seat add-on.
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

    for r in N.ESCALATION_RULES:
        db.add(EscalationRule(workspace_id=ws.id, **r))

    for i, (ref, subject, category, priority, status, group, ago, body) in enumerate(N.TICKETS):
        db.add(Ticket(workspace_id=ws.id, customer_id=by_ref[ref].id, number=f"NS-{901 + i}",
                      subject=subject, body=body, category=category, priority=priority, status=status,
                      group=group, source="seed", created_at=N.days_ago(ago, now), updated_at=N.days_ago(ago, now)))
    db.flush()

    for key, ref, subject, body, minutes_ago in N.REQUESTS:
        c = by_ref[ref]
        db.add(SupportRequest(workspace_id=ws.id, customer_id=c.id, submitted_via="seed", from_name=c.contact_name,
                              from_email=c.contact_email, subject=subject, body=body, scenario_key=key,
                              is_template=True, state="received", received_at=now - timedelta(minutes=minutes_ago)))

    for slug, title in N.DOCS:
        ingest_document(db, ws.id, slug, title, (DOCS_DIR / f"{slug}.md").read_text())
    db.flush()
    return ws


def reset_workspace(db: Session, slug: str) -> None:
    db.execute(delete(Workspace).where(Workspace.slug == slug))
    db.flush()
