import re
import unicodedata
from sqlalchemy.orm import Session
from sqlalchemy import Text,cast, func, literal, or_, select

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk

HYBRID_POOL_SIZE = 80
RRF_K = 60
PHRASE_POOL_SIZE = 40
QUERY_STOPWORDS = {
    "anh", "chị", "em", "tôi", "mình", "bạn", "cho", "hỏi", "hỏi",
    "về", "và", "hoặc", "là", "có", "không", "được", "bị", "thì",
    "như", "nào", "gì", "ra", "sao", "theo", "trong", "của", "các",
    "những", "người", "giữa", "một", "này", "đó", "ở", "tại",
}


def _trim_chunk_content(content: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", content).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rsplit(' ', 1)[0]}..."


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D")


def _normalize_for_match(text: str) -> str:
    text = _strip_accents(text).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def _query_terms(query: str) -> list[str]:
    normalized = _normalize_for_match(query)
    return [
        term for term in normalized.split()
        if len(term) > 1 and term not in QUERY_STOPWORDS
    ]


def _query_phrases(query: str) -> list[str]:
    terms = _query_terms(query)
    phrases: list[str] = []
    for size in (4, 3, 2):
        for i in range(0, len(terms) - size + 1):
            phrase = " ".join(terms[i:i + size])
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases[:12]


def _lexical_bonus(query: str, content: str) -> float:
    normalized_content = _normalize_for_match(content)
    terms = _query_terms(query)
    if not terms:
        return 0.0

    matched_terms = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", normalized_content))
    bonus = 0.02 * (matched_terms / len(terms))

    for phrase in _query_phrases(query):
        if phrase in normalized_content:
            word_count = len(phrase.split())
            bonus += 0.04 * max(word_count - 1, 1)

    return bonus


def _metadata_text(chunk: DocumentChunk) -> str:
    metadata = chunk.chunk_metadata or {}
    parts = [
        str(metadata.get("title", "")),
        str(metadata.get("article_title", "")),
        str(metadata.get("article", "")),
        str(metadata.get("clause", "")),
        str(metadata.get("chapter", "")),
    ]
    return " ".join(part for part in parts if part)


def search_similar_chunks(
    db: Session,
    query: str,
    query_embedding: list[float],
    owner_id: int,
    k: int = 8,
    source_ids: list[int] | None = None,
) -> list:
    """Hybrid retrieval: vector similarity + lexical match trên content/metadata."""
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

    phrase_filters = [
        func.immutable_unaccent(DocumentChunk.content).ilike(f"%{phrase}%")
        for phrase in _query_phrases(query)
    ]
    phrase_rows = []
    if phrase_filters:
        phrase_rows = list(db.execute(
            base_stmt
            .where(or_(*phrase_filters))
            .limit(PHRASE_POOL_SIZE)
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

    for rank, row in enumerate(phrase_rows, start=1):
        chunk = row[0]
        fused.setdefault(chunk.id, {"row": row, "score": 0.0})
        fused[chunk.id]["score"] += 0.05 + (1.0 / (RRF_K + rank))

    for item in fused.values():
        chunk = item["row"][0]
        item["score"] += _lexical_bonus(query, chunk.content)
        item["score"] += 0.5 * _lexical_bonus(query, _metadata_text(chunk))

    ranked = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
    return [item["row"] for item in ranked[:k]]
 
 
