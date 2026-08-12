import re
from sqlalchemy.orm import Session
from sqlalchemy import Text, cast, func, literal, select

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk

HYBRID_POOL_SIZE = 80
RRF_K = 60
LEXICAL_BONUS_WEIGHT = 0.012


def _trim_chunk_content(content: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", content).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rsplit(' ', 1)[0]}..."


def _normalize_lexical_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _query_terms(query: str) -> list[str]:
    terms = re.findall(r"\w+", _normalize_lexical_text(query), flags=re.UNICODE)
    return [term for term in terms if len(term) >= 2]


def _lexical_bonus(query: str, content: str) -> float:
    """Tinh diem thuong dua tren muc do khop tu khoa/cum tu voi chunk."""
    normalized_query = _normalize_lexical_text(query)
    normalized_content = _normalize_lexical_text(content)
    if not normalized_query or not normalized_content:
        return 0.0

    terms = _query_terms(normalized_query)
    if not terms:
        return 0.0

    matched_terms = sum(1 for term in set(terms) if term in normalized_content)
    term_score = matched_terms / len(set(terms))
    phrase_score = 1.0 if normalized_query in normalized_content else 0.0

    return LEXICAL_BONUS_WEIGHT * ((0.75 * term_score) + (0.25 * phrase_score))


def search_similar_chunks(
    db: Session,
    query: str,
    query_embedding: list[float],
    owner_id: int,
    k: int = 8,
    source_ids: list[int] | None = None,
) -> list:
    """Hybrid retrieval: vector similarity + PostgreSQL FTS rank."""
    base_stmt = (
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.owner_id == owner_id)
        .where(Document.status == DocumentStatus.COMPLETED)
    )
    if source_ids:
        base_stmt = base_stmt.where(DocumentChunk.document_id.in_(source_ids))

    vector_rows = list(db.execute(
        base_stmt
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(max(k, HYBRID_POOL_SIZE))
    ).all())

    searchable_text = (
        DocumentChunk.content
        + literal(" ")
        + func.coalesce(cast(DocumentChunk.chunk_metadata, Text), "")
        + literal(" ")
        + func.coalesce(Document.filename, "")
        + literal(" ")
        + func.coalesce(Document.file_type, "")
    )
    normalized_searchable_text = func.immutable_unaccent(searchable_text)
    normalized_query = func.immutable_unaccent(query)
    fts_vector = func.to_tsvector("simple", normalized_searchable_text)
    fts_query = func.plainto_tsquery("simple", normalized_query)
    fts_rank = func.ts_rank_cd(fts_vector, fts_query)
    lexical_rows = list(db.execute(
        base_stmt
        .where(fts_vector.op("@@")(fts_query))
        .order_by(fts_rank.desc())
        .limit(HYBRID_POOL_SIZE)
    ).all())

    fused: dict[int, dict] = {}
    for rank, row in enumerate(vector_rows, start=1):
        chunk = row[0]
        fused.setdefault(chunk.id, {"row": row, "score": 0.0})
        fused[chunk.id]["score"] += 1.0 / (RRF_K + rank)

    for rank, row in enumerate(lexical_rows, start=1):
        chunk = row[0]
        fused.setdefault(chunk.id, {"row": row, "score": 0.0})
        fused[chunk.id]["score"] += 1.0 / (RRF_K + rank)

    for item in fused.values():
        chunk, document = item["row"]
        searchable_content = " ".join(
            (
                chunk.content or "",
                str(chunk.chunk_metadata or ""),
                document.filename or "",
                document.file_type or "",
            )
        )
        item["score"] += _lexical_bonus(query, searchable_content)

    ranked = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
    return [item["row"] for item in ranked[:k]]
 
 
