"""Document import, import status, replace/delete lifecycle and retrieval exclusion (SPEC §6)."""
from sqlalchemy import select

from app import documents
from app.config import get_settings
from app.models import DocumentVersion, Workspace
from app.retrieval import search

from .conftest import new_workspace, upload

REFUNDS_V1 = "# Refunds\n\n## Window\nRefunds are allowed within 90 days of purchase.\n"
REFUNDS_V2 = "# Refunds\n\n## Window\nRefunds are allowed within 14 days of purchase.\n"


def _ws_id(db, slug):
    return db.scalar(select(Workspace.id).where(Workspace.slug == slug))


def test_markdown_and_text_import_reach_ready(reviewer):
    slug = new_workspace(reviewer)
    md = upload(reviewer, slug, "refunds.md", REFUNDS_V1)
    assert md.status_code == 202, md.text
    txt = upload(reviewer, slug, "hours.txt", "Support hours\n\nWe answer Monday to Friday.\n\nWeekends are closed.")
    assert txt.status_code == 202
    docs = {d["slug"]: d for d in reviewer.get(f"/api/w/{slug}/admin/documents").json()["documents"]}
    assert docs["refunds"]["status"] == "active" and docs["refunds"]["versions"][0]["import_status"] == "ready"
    assert docs["hours"]["versions"][0]["format"] == "text"
    detail = reviewer.get(f"/api/w/{slug}/admin/documents/{docs['refunds']['id']}").json()
    assert [s["section"] for s in detail["sections"]] == ["Window"] and "90 days" in detail["content"]


def test_unsupported_types_and_oversize_are_rejected(reviewer, db):
    slug = new_workspace(reviewer)
    for name in ("policy.pdf", "policy.docx", "page.html", "noext"):
        r = upload(reviewer, slug, name, "hello")
        assert r.status_code == 415 and ".md" in r.json()["detail"] and ".txt" in r.json()["detail"], name
    big = "x" * (get_settings().max_upload_bytes + 1)
    r = upload(reviewer, slug, "big.md", big)
    assert r.status_code == 413 and "MAX_UPLOAD_BYTES" in r.json()["detail"]
    assert upload(reviewer, slug, "nul.txt", "a\x00b").status_code == 415
    assert upload(reviewer, slug, "empty.md", "   ").status_code == 422
    assert reviewer.get(f"/api/w/{slug}/admin/documents").json()["documents"] == []  # nothing stored


def test_document_count_limit(reviewer, monkeypatch):
    slug = new_workspace(reviewer)
    monkeypatch.setattr(get_settings(), "max_documents_per_workspace", 2)
    assert upload(reviewer, slug, "a.md", "# A\n\n## S\nAlpha.").status_code == 202
    assert upload(reviewer, slug, "b.md", "# B\n\n## S\nBeta.").status_code == 202
    r = upload(reviewer, slug, "c.md", "# C\n\n## S\nGamma.")
    assert r.status_code == 409 and "limit" in r.json()["detail"]


def test_status_transitions_pending_processing_ready_and_failed(reviewer, db):
    slug = new_workspace(reviewer)
    ws_id = _ws_id(db, slug)
    v = documents.create_document(db, ws_id, "guide.md", "# Guide\n\n## Steps\nDo the thing.", "test")
    db.commit()
    assert (v.import_status, v.status) == ("pending", "pending")
    seen = []
    orig = documents.index_version

    def spy(session, version, actor):
        seen.append(session.get(DocumentVersion, version.id).import_status)
        return orig(session, version, actor)

    documents.index_version = spy
    try:
        v = documents.process_version(db, v.id, "test")
    finally:
        documents.index_version = orig
    assert seen == ["processing"] and (v.import_status, v.status) == ("ready", "active")
    # A file with a title but no body text fails with an error and never becomes searchable.
    bad = documents.create_document(db, ws_id, "blank.md", "# Only a title\n", "test")
    db.commit()
    bad = documents.process_version(db, bad.id, "test")
    assert bad.import_status == "failed" and bad.import_error == "No text content found."
    assert bad.status == "failed"


def test_replace_supersedes_and_delete_removes_from_retrieval(reviewer, db):
    slug = new_workspace(reviewer)
    ws_id = _ws_id(db, slug)
    doc = upload(reviewer, slug, "refunds.md", REFUNDS_V1).json()
    assert upload(reviewer, slug, "refunds.md", REFUNDS_V1, doc["id"]).status_code == 409  # identical
    r = upload(reviewer, slug, "refunds-2026.md", REFUNDS_V2, doc["id"])
    assert r.status_code == 202 and r.json()["versions"][0]["import_status"] == "pending"
    after = reviewer.get(f"/api/w/{slug}/admin/documents/{doc['id']}").json()
    versions = {v["version"]: v for v in after["versions"]}
    assert after["id"] == doc["id"] and after["version"]["version"] == 2  # stable document id
    assert versions[1]["status"] == "superseded" and versions[2]["status"] == "active"
    hits = search(db, ws_id, "refund window days", 5)
    assert hits and all("14 days" in h.text and h.version == 2 for h in hits)
    db.rollback()
    d = reviewer.delete(f"/api/w/{slug}/admin/documents/{doc['id']}").json()
    assert d["status"] == "deleted" and all(v["status"] in ("superseded", "deleted") for v in d["versions"])
    assert search(db, ws_id, "refund window days", 5) == []
    db.rollback()
    assert reviewer.delete(f"/api/w/{slug}/admin/documents/{doc['id']}").status_code == 409
    assert upload(reviewer, slug, "refunds.md", REFUNDS_V2, doc["id"]).status_code == 409  # deleted: no replace
    # The same file name can be imported again as a new document with a new id.
    again = upload(reviewer, slug, "refunds.md", REFUNDS_V2).json()
    again = reviewer.get(f"/api/w/{slug}/admin/documents/{again['id']}").json()
    assert again["id"] != doc["id"] and again["status"] == "active"
