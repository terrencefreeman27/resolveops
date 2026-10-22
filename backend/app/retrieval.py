"""Document ingestion and embedding retrieval (pgvector).

Embeddings come from a local ONNX model (fastembed, BAAI/bge-small-en-v1.5, 384-dim), so
retrieval is real in both demo and live mode without any API key.
Only chunks of the *current active version* of a non-deleted document are searchable; the
document lifecycle (import, replace, delete) lives in documents.py.
"""
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Chunk, Document, DocumentVersion

MAX_SECTION_CHARS = 1800


@lru_cache
def _model():
    from fastembed import TextEmbedding  # imported lazily: loading the model takes ~1s

    return TextEmbedding(get_settings().embedding_model)


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(_model().query_embed([text]))).tolist()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:150] or "section"


@dataclass
class Section:
    title: str
    body: str


def split_sections(content: str, fmt: str = "markdown") -> tuple[str | None, list[Section]]:
    """Split a Markdown document on H2 headings. Text before the first H2 becomes 'Overview'.
    Plain text is split on blank-line paragraphs grouped up to MAX_SECTION_CHARS."""
    if fmt == "text":
        paras = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
        out, buf = [], ""
        for p in paras:
            if buf and len(buf) + len(p) > MAX_SECTION_CHARS:
                out.append(Section(f"Part {len(out) + 1}", buf))
                buf = ""
            buf = f"{buf}\n\n{p}".strip()
        if buf:
            out.append(Section(f"Part {len(out) + 1}", buf))
        return None, out

    title = None
    sections: list[Section] = []
    current, lines = "Overview", []
    for line in content.splitlines():
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if "\n".join(lines).strip():
                sections.append(Section(current, "\n".join(lines).strip()))
            current, lines = line[3:].strip(), []
            continue
        lines.append(line)
    if "\n".join(lines).strip():
        sections.append(Section(current, "\n".join(lines).strip()))
    # Very long sections are split on paragraphs so each chunk stays focused.
    out: list[Section] = []
    for s in sections:
        if len(s.body) <= MAX_SECTION_CHARS:
            out.append(s)
            continue
        part, buf = 1, ""
        for p in re.split(r"\n\s*\n", s.body):
            if buf and len(buf) + len(p) > MAX_SECTION_CHARS:
                out.append(Section(f"{s.title} ({part})", buf))
                part, buf = part + 1, ""
            buf = f"{buf}\n\n{p}".strip()
        if buf:
            out.append(Section(f"{s.title} ({part})" if part > 1 else s.title, buf))
    return title, out


def ingest_document(db: Session, workspace_id: uuid.UUID, slug: str, title: str, content: str,
                    fmt: str = "markdown"):
    """Kept for callers of the M1 API; the lifecycle lives in documents.py."""
    from .documents import ingest_document as _ingest

    return _ingest(db, workspace_id, slug, title, content, fmt)


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    version: int
    doc_slug: str
    doc_title: str
    section: str
    text: str
    score: float


def search(db: Session, workspace_id: uuid.UUID, query: str, top_k: int) -> list[Hit]:
    """Cosine-similarity search over the workspace's active chunks only."""
    qvec = embed_query(query)
    # With filters, let the HNSW scan continue until enough matching rows are found (pgvector >= 0.8).
    db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    distance = Chunk.embedding.cosine_distance(qvec)
    rows = db.execute(
        select(Chunk, Document.slug, Document.title, DocumentVersion.version, distance.label("distance"))
        .join(Document, Document.id == Chunk.document_id)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .where(
            Chunk.workspace_id == workspace_id,
            Chunk.active.is_(True),
            Document.status == "active",
            DocumentVersion.status == "active",
        )
        .order_by(distance)
        .limit(top_k)
    ).all()
    return [
        Hit(c.id, c.document_id, c.document_version_id, ver, slug, title, c.section, c.text, round(1 - float(d), 4))
        for c, slug, title, ver, d in rows
    ]
