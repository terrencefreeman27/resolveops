"""Reviewer onboarding and workspace administration (SPEC §2). Reviewer-only, enforced server-side:
every route depends on a signed-in reviewer who is a member of *this* workspace (require_reviewer),
except creating a workspace, which needs any signed-in reviewer and makes them its first member.

Steps: (1) create workspace + company details, (2) import .md/.txt documents, (3) import status and
document contents, (4) escalation rules, (5) ticket adapter, (6) test a sample request.
"""
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, documents, evidence, rules, staleness
from ..adapters import github
from ..config import get_settings
from ..context import Actor, current_reviewer, require_reviewer
from ..db import SessionLocal, get_db
from ..models import Chunk, Document, DocumentVersion, EscalationRule, Membership, Workspace
from ..retrieval import search

router = APIRouter(prefix="/api")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
CATEGORIES = ["access", "billing", "product_issue"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompanyIn(In):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=42)
    tagline: str = Field(default="", max_length=300)
    industry: str = Field(default="", max_length=120)
    support_hours: str = Field(default="", max_length=120)
    support_signature: str = Field(default="", max_length=120)
    ticket_groups: list[str] = Field(default_factory=lambda: ["Support", "Billing", "Engineering"],
                                     min_length=1, max_length=12)


def _clean_groups(groups: list[str]) -> list[str]:
    out = list(dict.fromkeys(g.strip()[:64] for g in groups if g.strip()))
    if not out:
        raise HTTPException(422, "At least one ticket group is required.")
    return out


def _profile(body: CompanyIn) -> dict:
    return {"tagline": body.tagline.strip(), "industry": body.industry.strip(),
            "support_hours": body.support_hours.strip(),
            "support_signature": body.support_signature.strip() or f"{body.name.strip()} Support", "fictional": False}


# --- step 1: workspace + company details ---------------------------------------------------

@router.post("/workspaces")
def create_workspace(body: CompanyIn, request: Request, db: Session = Depends(get_db)):
    reviewer = current_reviewer(request, db)
    if reviewer is None:
        raise HTTPException(403, "Reviewer sign-in required to create a workspace.")
    owned = db.scalar(select(func.count()).select_from(Membership).where(Membership.reviewer_id == reviewer.id))
    if owned >= get_settings().max_workspaces_per_reviewer + 2:  # +2: the seeded demo workspaces
        raise HTTPException(409, "Workspace limit reached for this reviewer.")
    slug = (body.slug or re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-"))[:40]
    if not SLUG_RE.match(slug):
        raise HTTPException(422, "Workspace id must be 2-41 lowercase letters, digits or hyphens.")
    if db.scalar(select(Workspace.id).where(Workspace.slug == slug)):
        raise HTTPException(409, f"A workspace with id '{slug}' already exists.")
    groups = _clean_groups(body.ticket_groups)
    ws = Workspace(slug=slug, name=body.name.strip(), profile=_profile(body), settings={
        "ticket_prefix": re.sub(r"[^A-Z]", "", body.name.upper())[:3] or "WS", "ticket_adapter": "internal",
        "demo_enabled": False, "roles": {}, "admin_roles": ["Admin", "Owner"], "ticket_groups": groups,
        "evidence_review_group": groups[0], "supported_categories": CATEGORIES, "demo_scenarios": []})
    db.add(ws)
    db.flush()
    db.add(Membership(reviewer_id=reviewer.id, workspace_id=ws.id, role="admin"))
    audit.record(db, workspace_id=ws.id, actor=f"reviewer:{reviewer.email}", event="workspace.created",
                 summary={"slug": slug, "name": ws.name})
    db.commit()
    return _settings_dict(ws)


def _settings_dict(ws: Workspace) -> dict:
    s = ws.settings
    return {"slug": ws.slug, "name": ws.name, "profile": ws.profile,
            "settings": {k: s.get(k) for k in ("ticket_adapter", "ticket_groups", "evidence_review_group",
                                                "demo_enabled", "supported_categories", "retrieval_min_score")},
            "retrieval_min_score": evidence.threshold_for(ws)}


@router.put("/w/{ws}/admin/company")
def update_company(body: CompanyIn, actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    ws = db.get(Workspace, actor.workspace_id)
    groups = _clean_groups(body.ticket_groups)
    used = set(db.scalars(select(EscalationRule.outcome["group"].astext).where(EscalationRule.workspace_id == ws.id)))
    missing = sorted(g for g in used if g and g not in groups)
    if missing:
        raise HTTPException(409, f"Escalation rules still route to {', '.join(missing)}; change those rules first.")
    ws.name = body.name.strip()
    ws.profile = _profile(body) | {"fictional": ws.profile.get("fictional", False)}
    ws.settings = {**ws.settings, "ticket_groups": groups,
                   "evidence_review_group": ws.settings.get("evidence_review_group")
                   if ws.settings.get("evidence_review_group") in groups else groups[0]}
    audit.record(db, workspace_id=ws.id, actor=actor.label, event="workspace.updated", summary={"name": ws.name})
    db.commit()
    return _settings_dict(ws)


# --- step 5: ticket adapter ------------------------------------------------------------------

def _adapters() -> list[dict]:
    """Availability is decided server-side from config; the token itself never leaves the server."""
    gh = github.status()
    return [
        {"name": "internal", "label": "Internal tickets", "available": True, "configured": True,
         "detail": "Tickets are stored in ResolveOps. Works in demo and live mode."},
        {"name": "github", "label": "GitHub Issues", "available": gh.available, "configured": gh.available,
         "repo": gh.repo if gh.available else None,
         "detail": (f"Approved escalations create an issue in {gh.repo}; other tickets and notes stay internal. "
                    "Visitor sandboxes always use internal tickets." if gh.available else
                    f"Not configured: {gh.reason} See README \"Optional GitHub Issues integration\".")},
    ]


@router.get("/w/{ws}/admin/adapters")
def list_adapters(actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    ws = db.get(Workspace, actor.workspace_id)
    return {"selected": ws.settings.get("ticket_adapter", "internal"), "adapters": _adapters()}


class AdapterIn(In):
    adapter: str = Field(max_length=32)


@router.put("/w/{ws}/admin/adapter")
def select_adapter(body: AdapterIn, actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    adapters = _adapters()
    spec = next((a for a in adapters if a["name"] == body.adapter), None)
    if spec is None:
        raise HTTPException(422, "Unknown ticket adapter.")
    if not spec["available"]:
        raise HTTPException(409, f"{spec['label']} is not configured on this server.")
    ws = db.get(Workspace, actor.workspace_id)
    ws.settings = {**ws.settings, "ticket_adapter": spec["name"]}
    audit.record(db, workspace_id=ws.id, actor=actor.label, event="workspace.adapter_selected",
                 summary={"adapter": spec["name"]})
    db.commit()
    return {"selected": spec["name"], "adapters": adapters}


# --- steps 2-3: documents --------------------------------------------------------------------

class UploadIn(In):
    filename: str = Field(min_length=1, max_length=200)
    # Text of the file, read by the browser. Size is checked in bytes against MAX_UPLOAD_BYTES.
    content: str = Field(max_length=2_000_000)


def _process_in_background(version_id: uuid.UUID, actor: str) -> None:
    with SessionLocal() as db:
        documents.process_version(db, version_id, actor)


def _rejected(exc: documents.ImportRejected):
    raise HTTPException(exc.status_code, str(exc))


def _version_dict(v: DocumentVersion) -> dict:
    return {"id": str(v.id), "version": v.version, "status": v.status, "import_status": v.import_status,
            "import_error": v.import_error, "format": v.source_format, "filename": v.filename,
            "size_bytes": v.size_bytes, "policy_facts": v.policy_facts, "created_by": v.created_by,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "retired_at": v.retired_at.isoformat() if v.retired_at else None}


def _doc_dict(db: Session, d: Document, with_versions: bool = True) -> dict:
    out = {"id": str(d.id), "slug": d.slug, "title": d.title, "status": d.status,
           "current_version_id": str(d.current_version_id) if d.current_version_id else None,
           "deleted_at": d.deleted_at.isoformat() if d.deleted_at else None}
    if with_versions:
        versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id)
                              .order_by(DocumentVersion.version.desc())).all()
        out["versions"] = [_version_dict(v) for v in versions]
    return out


def _own_doc(db: Session, actor: Actor, doc_id: uuid.UUID) -> Document:
    d = db.scalar(select(Document).where(Document.id == doc_id, Document.workspace_id == actor.workspace_id))
    if d is None:
        raise HTTPException(404, "Document not found.")
    return d


@router.get("/w/{ws}/admin/documents")
def list_documents(actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    s = get_settings()
    docs = db.scalars(select(Document).where(Document.workspace_id == actor.workspace_id).order_by(Document.title)).all()
    return {"documents": [_doc_dict(db, d) for d in docs],
            "limits": {"max_upload_bytes": s.max_upload_bytes, "max_documents": s.max_documents_per_workspace,
                       "formats": sorted(documents.FORMATS), "note": documents.SUPPORTED_NOTE}}


@router.post("/w/{ws}/admin/documents", status_code=202)
def import_document(body: UploadIn, background: BackgroundTasks, actor: Actor = Depends(require_reviewer),
                    db: Session = Depends(get_db)):
    try:
        v = documents.create_document(db, actor.workspace_id, body.filename, body.content, actor.label)
    except documents.ImportRejected as exc:
        _rejected(exc)
    db.commit()
    background.add_task(_process_in_background, v.id, actor.label)
    return _doc_dict(db, db.get(Document, v.document_id))


@router.post("/w/{ws}/admin/documents/{doc_id}/versions", status_code=202)
def replace_document(doc_id: uuid.UUID, body: UploadIn, background: BackgroundTasks,
                     actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    d = _own_doc(db, actor, doc_id)
    try:
        v = documents.create_replacement(db, d, body.filename, body.content, actor.label)
    except documents.ImportRejected as exc:
        _rejected(exc)
    db.commit()
    background.add_task(_process_in_background, v.id, actor.label)
    return _doc_dict(db, d)


@router.delete("/w/{ws}/admin/documents/{doc_id}")
def delete_document(doc_id: uuid.UUID, actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    d = _own_doc(db, actor, doc_id)
    try:
        stale = documents.delete_document(db, d, actor.label)
    except documents.ImportRejected as exc:
        _rejected(exc)
    db.commit()
    return _doc_dict(db, d) | {"proposals_marked_stale": len(stale)}


@router.get("/w/{ws}/admin/documents/{doc_id}")
def get_document(doc_id: uuid.UUID, version: int | None = None, actor: Actor = Depends(require_reviewer),
                 db: Session = Depends(get_db)):
    """Document contents and sections for one version (default: current, else latest)."""
    d = _own_doc(db, actor, doc_id)
    q = select(DocumentVersion).where(DocumentVersion.document_id == d.id)
    v = (db.scalar(q.where(DocumentVersion.version == version)) if version is not None
         else db.get(DocumentVersion, d.current_version_id) if d.current_version_id
         else db.scalar(q.order_by(DocumentVersion.version.desc()).limit(1)))
    if v is None:
        raise HTTPException(404, "Version not found.")
    chunks = db.scalars(select(Chunk).where(Chunk.document_version_id == v.id).order_by(Chunk.ordinal)).all()
    return _doc_dict(db, d) | {"version": _version_dict(v), "content": v.content, "sections": [
        {"chunk_id": str(c.id), "ordinal": c.ordinal, "section": c.section, "text": c.text, "active": c.active,
         "policy_facts": c.policy_facts} for c in chunks]}


# --- step 4: escalation rules ----------------------------------------------------------------

class RuleIn(In):
    key: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=500)
    categories: list[str] = Field(default_factory=list, max_length=3)
    keywords_any: list[str] = Field(default_factory=list, max_length=25)
    plans_any: list[str] = Field(default_factory=list, max_length=10)
    action: str = Field(default="escalate", pattern="^(escalate|note)$")
    group: str | None = Field(default=None, max_length=64)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    note: str | None = Field(default=None, max_length=300)
    enabled: bool = True


def _rule_dict(r: EscalationRule) -> dict:
    return {"id": str(r.id), "key": r.key, "name": r.name, "description": r.description,
            "condition": r.condition, "outcome": r.outcome, "enabled": r.enabled}


def _apply_rule(ws: Workspace, r: EscalationRule, body: RuleIn) -> None:
    if body.action == "escalate" and body.group not in ws.settings.get("ticket_groups", []):
        raise HTTPException(422, "Escalation group must be one of this workspace's ticket groups.")
    if any(c not in CATEGORIES for c in body.categories):
        raise HTTPException(422, f"Categories must be among {', '.join(CATEGORIES)}.")
    kws = [k.strip().lower() for k in body.keywords_any if k.strip()]
    if not (body.categories or kws or body.plans_any):
        raise HTTPException(422, "A rule needs at least one condition (category, keyword or plan).")
    r.name, r.description = body.name.strip(), body.description.strip() or body.name.strip()
    r.condition = {k: v for k, v in {"categories": body.categories, "keywords_any": kws,
                                     "plans_any": [p.strip() for p in body.plans_any if p.strip()]}.items() if v}
    r.outcome = ({"next_action": "escalate", "group": body.group, "priority": body.priority, "human_only": True}
                 if body.action == "escalate" else {"human_only": True, "note": body.note or "Human handling required"})
    r.enabled = body.enabled


def _rules_changed(db: Session, actor: Actor, change: str) -> dict:
    db.flush()
    stale = staleness.invalidate_for_rule_change(db, actor.workspace_id, change, actor.label)
    audit.record(db, workspace_id=actor.workspace_id, actor=actor.label, event="rules.changed",
                 summary={"change": change, "proposals_marked_stale": len(stale)})
    db.commit()
    return {"proposals_marked_stale": len(stale)}


@router.get("/w/{ws}/admin/rules")
def list_rules(actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(EscalationRule).where(EscalationRule.workspace_id == actor.workspace_id)
                      .order_by(EscalationRule.key)).all()
    ws = db.get(Workspace, actor.workspace_id)
    return {"rules": [_rule_dict(r) for r in rows], "ticket_groups": ws.settings.get("ticket_groups", []),
            "categories": CATEGORIES}


@router.post("/w/{ws}/admin/rules")
def create_rule(body: RuleIn, actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    ws = db.get(Workspace, actor.workspace_id)
    key = (body.key or re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-"))[:64]
    if not key or db.scalar(select(EscalationRule.id).where(EscalationRule.workspace_id == ws.id,
                                                            EscalationRule.key == key)):
        raise HTTPException(409, f"A rule with key '{key}' already exists.")
    r = EscalationRule(workspace_id=ws.id, key=key, name="", description="", condition={}, outcome={})
    _apply_rule(ws, r, body)
    db.add(r)
    changed = _rules_changed(db, actor, f"added '{r.name}'")  # flushes, so r.id is set
    return _rule_dict(r) | changed


@router.put("/w/{ws}/admin/rules/{rule_id}")
def update_rule(rule_id: uuid.UUID, body: RuleIn, actor: Actor = Depends(require_reviewer),
                db: Session = Depends(get_db)):
    ws = db.get(Workspace, actor.workspace_id)
    r = db.scalar(select(EscalationRule).where(EscalationRule.id == rule_id, EscalationRule.workspace_id == ws.id))
    if r is None:
        raise HTTPException(404, "Rule not found.")
    _apply_rule(ws, r, body)
    changed = _rules_changed(db, actor, f"updated '{r.name}'")
    return _rule_dict(r) | changed


@router.delete("/w/{ws}/admin/rules/{rule_id}")
def delete_rule(rule_id: uuid.UUID, actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    r = db.scalar(select(EscalationRule).where(EscalationRule.id == rule_id,
                                               EscalationRule.workspace_id == actor.workspace_id))
    if r is None:
        raise HTTPException(404, "Rule not found.")
    name = r.name
    db.delete(r)
    return {"deleted": True} | _rules_changed(db, actor, f"deleted '{name}'")


# --- step 6: test a sample request -----------------------------------------------------------

class TestRequestIn(In):
    text: str = Field(min_length=3, max_length=4000)
    category: str = Field(default="access", pattern="^(access|billing|product_issue)$")
    plan: str | None = Field(default=None, max_length=32)


@router.post("/w/{ws}/admin/test-request")
def test_request(body: TestRequestIn, actor: Actor = Depends(require_reviewer), db: Session = Depends(get_db)):
    """Dry run of the deterministic parts of the workflow against this workspace's configuration:
    retrieval over its active documents, the evidence check, and its escalation rules. Nothing is stored,
    no AI model is called, and no ticket is created."""
    hits = search(db, actor.workspace_id, body.text, get_settings().retrieval_top_k)
    from ..schemas import Passage
    passages = [Passage(**h.__dict__) for h in hits]
    check = evidence.assess(db, actor.workspace_id, passages)
    matched = rules.evaluate(db, actor.workspace_id, category=body.category, text=body.text, plan=body.plan)
    escalate = next((r for r, _ in matched if r.outcome.get("next_action") == "escalate"), None)
    if escalate is not None:
        floor = f"escalate to {escalate.outcome.get('group')} ({escalate.outcome.get('priority')}) by rule '{escalate.name}'"
    elif check.status != "sufficient":
        floor = f"clarify or escalate ({check.status} evidence); a confident resolve is not allowed"
    else:
        floor = "any (resolve allowed if the drafted answer cites the passages above)"
    db.rollback()
    return {"passages": [{"chunk_id": str(p.chunk_id), "doc_title": p.doc_title, "version": p.version,
                          "section": p.section, "score": p.score, "relevant": p.score >= check.threshold,
                          "excerpt": p.text[:240]} for p in passages],
            "evidence_check": check.model_dump(mode="json"),
            "rule_hits": [h.model_dump() for _, h in matched],
            "allowed_outcome": floor,
            "note": "Dry run: retrieval, evidence check and escalation rules only. No AI model was called and "
                    "nothing was stored. In live mode, submitted requests run the full workflow."}
