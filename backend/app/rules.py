"""Deterministic escalation rules — evaluated by application code, not by the model."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EscalationRule
from .schemas import RuleHit


def evaluate(db: Session, workspace_id, *, category: str, text: str, plan: str | None) -> list[tuple[EscalationRule, RuleHit]]:
    lowered = text.lower()
    hits = []
    rules = db.scalars(select(EscalationRule).where(
        EscalationRule.workspace_id == workspace_id, EscalationRule.enabled.is_(True)).order_by(EscalationRule.key)).all()
    for rule in rules:
        c = rule.condition
        if c.get("categories") and category not in c["categories"]:
            continue
        if c.get("plans_any") and plan not in c["plans_any"]:
            continue
        if c.get("keywords_any") and not any(k.lower() in lowered for k in c["keywords_any"]):
            continue
        o = rule.outcome
        if o.get("next_action") == "escalate":
            effect = f"Escalate to {o.get('group')} ({o.get('priority')})"
        else:
            effect = o.get("note", "Human handling required")
        hits.append((rule, RuleHit(key=rule.key, name=rule.name, effect=effect)))
    return hits
