"""Knowledge-base document lifecycle (SPEC §6).

- Stable document ids; every import or replacement is a new numbered version.
- Import status per version: pending -> processing -> ready | failed (with an error message).
- Lifecycle status per version: pending -> active -> superseded | deleted (or failed).
- Replacing activates the new version, supersedes the old one, deactivates its chunks and marks
  dependent pending proposals stale — all in one transaction (staleness.py).
- Deleting is a soft delete: the document and its versions stay for audit and for citations that
  already point at them, but their chunks leave retrieval in the same transaction.
- Only Markdown and plain text are accepted. Size and per-workspace document-count limits apply.
"""
import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import audit, staleness
from .config import get_settings
from .models import Chunk, Document, DocumentVersion
from .retrieval import embed_passages, slugify, split_sections

FORMATS = {".md": "markdown", ".markdown": "markdown", ".txt": "text"}
SUPPORTED_NOTE = "Only Markdown (.md) and plain-text (.txt) files can be imported."

# Policy markers: <!-- policy billing.refund_window_days: 30 --> inside a section. They let the
# evidence check detect two current documents that disagree on the same fact (evidence.py).
POLICY_RE = re.compile(r"<!--\s*policy\s+([a-z0-9_.\-]+)\s*:\s*(.+?)\s*-->", re.IGNORECASE)


class ImportRejected(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_policy_facts(text: str) -> dict[str, str]:
    return {k.lower(): v.strip() for k, v in POLICY_RE.findall(text)}


def check_upload(filename: str, content: str) -> str:
    """Validate an upload before anything is stored. Returns the source format."""
    name = PurePosixPath(filename.replace("\\", "/")).name
    ext = PurePosixPath(name.lower()).suffix
    if ext not in FORMATS:
        raise ImportRejected(f"'{name}' is not supported. {SUPPORTED_NOTE} PDF, Word, HTML and other formats are "
                             "not imported.", 415)
    limit = get_settings().max_upload_bytes
    size = len(content.encode("utf-8"))
    if size > limit:
        raise ImportRejected(f"'{name}' is {size:,} bytes; the limit is {limit:,} bytes (MAX_UPLOAD_BYTES).", 413)
    if "\x00" in content:
        raise ImportRejected(f"'{name}' looks like a binary file. {SUPPORTED_NOTE}", 415)
    if not content.strip():
        raise ImportRejected(f"'{name}' is empty.", 422)
    return FORMATS[ext]


def _title_from(filename: str) -> str:
    stem = PurePosixPath(filename.replace("\\", "/")).stem
    return re.sub(r"[-_]+", " ", stem).strip().title() or "Untitled"


def _new_version(db: Session, doc: Document, filename: str, content: str, fmt: str, actor: str) -> DocumentVersion:
    prev = db.scalar(select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == doc.id))
    v = DocumentVersion(workspace_id=doc.workspace_id, document_id=doc.id, version=(prev or 0) + 1,
                        content=content, content_hash=hashlib.sha256(content.encode()).hexdigest(),
                        source_format=fmt, status="pending", import_status="pending", filename=filename[:200],
                        size_bytes=len(content.encode("utf-8")), created_by=actor)
    db.add(v)
    db.flush()
    return v


def create_document(db: Session, workspace_id: uuid.UUID, filename: str, content: str, actor: str,
                    title: str | None = None, slug: str | None = None) -> DocumentVersion:
    """Register a new document and its first version (import_status 'pending'). Does not index."""
    fmt = check_upload(filename, content)
    live_docs = db.scalar(select(func.count()).select_from(Document).where(
        Document.workspace_id == workspace_id, Document.status != "deleted"))
    limit = get_settings().max_documents_per_workspace
    if live_docs >= limit:
        raise ImportRejected(f"This workspace already has {live_docs} documents; the limit is {limit} "
                             "(MAX_DOCUMENTS_PER_WORKSPACE). Delete or replace a document instead.", 409)
    base = slug or slugify(PurePosixPath(filename.replace("\\", "/")).stem)
    existing = db.scalar(select(Document).where(Document.workspace_id == workspace_id, Document.slug == base))
    if existing is not None and existing.status != "deleted":
        raise ImportRejected(f"A document named '{existing.title}' ({base}) already exists. Use Replace to upload "
                             "a new version.", 409)
    final_slug, n = base, 1
    while db.scalar(select(Document.id).where(Document.workspace_id == workspace_id, Document.slug == final_slug)):
        n += 1
        final_slug = f"{base}-{n}"
    doc = Document(workspace_id=workspace_id, slug=final_slug, title=(title or _title_from(filename))[:300],
                   status="pending", created_by=actor)
    db.add(doc)
    db.flush()
    return _new_version(db, doc, filename, content, fmt, actor)


def create_replacement(db: Session, doc: Document, filename: str, content: str, actor: str) -> DocumentVersion:
    """Register a new version of an existing document (import_status 'pending'). Does not index."""
    fmt = check_upload(filename, content)
    if doc.status == "deleted":
        raise ImportRejected("This document was deleted; import it as a new document instead.", 409)
    pending = db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id,
                                                         DocumentVersion.import_status.in_(("pending", "processing"))))
    if pending:
        raise ImportRejected("A version of this document is still being imported; wait for it to finish.", 409)
    current = db.get(DocumentVersion, doc.current_version_id) if doc.current_version_id else None
    if current is not None and current.content_hash == hashlib.sha256(content.encode()).hexdigest():
        raise ImportRejected(f"The file is identical to the current version (v{current.version}); nothing to replace.", 409)
    return _new_version(db, doc, filename, content, fmt, actor)


def index_version(db: Session, v: DocumentVersion, actor: str) -> list[uuid.UUID]:
    """Chunk + embed a version and make it the document's active version, retiring the previous one
    and marking dependent pending proposals stale. No commit: runs inside the caller's transaction.
    Raises ImportRejected if the content has no indexable text. Returns request ids marked stale."""
    doc = db.get(Document, v.document_id)
    title, sections = split_sections(v.content, v.source_format)
    if not sections:
        raise ImportRejected("No text content found.")
    vectors = embed_passages([f"{doc.title}\n{s.title}\n{s.body}" for s in sections])
    facts: dict[str, str] = {}
    for i, (s, vec) in enumerate(zip(sections, vectors)):
        section_facts = parse_policy_facts(s.body)
        facts.update(section_facts)
        db.add(Chunk(workspace_id=v.workspace_id, document_id=doc.id, document_version_id=v.id, section=s.title,
                     section_slug=slugify(s.title), ordinal=i, text=s.body, embedding=vec, active=True,
                     policy_facts=section_facts))
    now = _now()
    retired = {}
    for old in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                                        DocumentVersion.id != v.id,
                                                        DocumentVersion.status == "active")):
        old.status, old.retired_at = "superseded", now
        retired[old.id] = staleness.describe_version(db, old, f"superseded by v{v.version}")
    db.execute(update(Chunk).where(Chunk.document_id == doc.id, Chunk.document_version_id != v.id).values(active=False))
    v.status, v.import_status, v.import_error = "active", "ready", None
    v.policy_facts, v.processed_at = facts, now
    doc.status, doc.current_version_id = "active", v.id
    if title and doc.title.lower() in (_title_from(v.filename or "").lower(), "untitled"):
        doc.title = title[:300]  # prefer the document's own H1 over a filename-derived title
    db.flush()
    stale = staleness.invalidate_for_document_versions(db, v.workspace_id, retired, actor)
    audit.record(db, workspace_id=v.workspace_id, actor=actor,
                 event="document.replaced" if retired else "document.imported",
                 summary={"document_id": str(doc.id), "title": doc.title, "version": v.version,
                          "sections": len(sections), "policy_facts": facts,
                          "superseded_version_ids": [str(x) for x in retired], "proposals_marked_stale": len(stale)})
    return stale


def process_version(db: Session, version_id: uuid.UUID, actor: str) -> DocumentVersion:
    """Run the import pipeline for a pending version, committing each status transition so the UI can
    show pending -> processing -> ready | failed. Activation and stale marking share one transaction."""
    v = db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id).with_for_update())
    if v is None or v.import_status != "pending":
        return v
    v.import_status = "processing"
    db.commit()
    try:
        index_version(db, v, actor)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - any failure is recorded on the version, nothing half-indexed
        db.rollback()
        v = db.get(DocumentVersion, version_id)
        doc = db.get(Document, v.document_id)
        v.import_status, v.status = "failed", "failed"
        v.import_error = (str(exc) or exc.__class__.__name__)[:500]
        if doc.current_version_id is None:
            doc.status = "failed"
        audit.record(db, workspace_id=v.workspace_id, actor=actor, event="document.import_failed",
                     summary={"document_id": str(doc.id), "version": v.version}, error=v.import_error)
        db.commit()
    return v


def delete_document(db: Session, doc: Document, actor: str) -> list[uuid.UUID]:
    """Soft delete: remove from retrieval and stale dependent pending proposals, in one transaction."""
    if doc.status == "deleted":
        raise ImportRejected("Document is already deleted.", 409)
    now = _now()
    retired = {}
    for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                                                      DocumentVersion.status == "active")):
        v.status, v.retired_at = "deleted", now
        retired[v.id] = staleness.describe_version(db, v, "deleted")
    db.execute(update(Chunk).where(Chunk.document_id == doc.id).values(active=False))
    doc.status, doc.deleted_at, doc.deleted_by = "deleted", now, actor
    db.flush()
    stale = staleness.invalidate_for_document_versions(db, doc.workspace_id, retired, actor)
    audit.record(db, workspace_id=doc.workspace_id, actor=actor, event="document.deleted",
                 summary={"document_id": str(doc.id), "title": doc.title, "proposals_marked_stale": len(stale)})
    return stale


def ingest_document(db: Session, workspace_id: uuid.UUID, slug: str, title: str, content: str,
                    fmt: str = "markdown", actor: str = "system:seed") -> DocumentVersion:
    """Synchronous import used by the seed loader and tests: create (or replace) and index in the
    caller's transaction."""
    ext = ".txt" if fmt == "text" else ".md"
    doc = db.scalar(select(Document).where(Document.workspace_id == workspace_id, Document.slug == slug))
    if doc is None or doc.status == "deleted":
        v = create_document(db, workspace_id, f"{slug}{ext}", content, actor, title=title, slug=slug)
    else:
        v = create_replacement(db, doc, f"{slug}{ext}", content, actor)
    v.import_status = "processing"
    index_version(db, v, actor)
    return v
