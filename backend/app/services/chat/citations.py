
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import select

from rag.service.emb_model import embed
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk


MAX_REFERENCE_CHUNKS = 10
CITATION_SIMILARITY_THRESHOLD = 0.45

def _assign_citations_by_similarity(
    sentences: list[str],
    chunk_lookup: dict[int, tuple],
    threshold: float = CITATION_SIMILARITY_THRESHOLD,
) -> list[tuple[str, int | None, float]]:
    """Với mỗi câu trong answer, tìm chunk nguồn (trong chunk_lookup) có
    embedding gần nhất theo cosine similarity. Nếu similarity cao nhất
    vẫn dưới threshold, câu đó không được gán nguồn (idx=None).
 
    Trả về list (sentence, chunk_index_or_None, best_similarity).
    """
    if not sentences:
        return []
 
    chunk_indices = list(chunk_lookup.keys())
    chunk_texts = [chunk_lookup[i][1].content.strip() for i in chunk_indices]
 
    # Encode theo batch 1 lần duy nhất (không encode từng câu/chunk riêng lẻ
    # để tránh gọi model nhiều lần không cần thiết).
    sentence_embeddings = embed(sentences)
    chunk_embeddings = embed(chunk_texts)
 
    assigned: list[tuple[str, int | None, float]] = []
    for sent, sent_emb in zip(sentences, sentence_embeddings):
        best_idx = None
        best_score = -1.0
        for idx, chunk_emb in zip(chunk_indices, chunk_embeddings):
            score = _cosine_sim(np.asarray(sent_emb), np.asarray(chunk_emb))
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_score < threshold:
            assigned.append((sent, None, best_score))
        else:
            assigned.append((sent, best_idx, best_score))
 
    return assigned

def _expand_with_reference(
    db: Session,
    results: list,
    owner_id: int,
    source_ids: list[int] | None = None,
    max_refs: int = MAX_REFERENCE_CHUNKS,
) -> list:
    """
    Voi moi chunk da chon o top-k, doc metadata['references'] (do buoc
    enrichment luc ingest sinh ra) va lay them cac Dieu/Khoan duoc tham
    chieu toi, neu co trong luat va chua co san trong top-k.
    """
    existing_ids = {row[0].id for row in results}
    seen_refs: set[tuple]= set()
    ref_targets: list[dict] = []

    for chunk, _document in results:
        refs = ( chunk.chunk_metadata or {}).get("references", [])
        for ref in refs:
            article = ref.get("article")
            if not article:
                continue
            key = (article, ref.get("clause"))
            if key in seen_refs:
                continue
            seen_refs.add(key)
            ref_targets.append(ref)

    if not ref_targets:
        return []
    ref_targets= ref_targets[:max_refs]
    base_stmt = (
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.owner_id == owner_id)
        .where(Document.status == DocumentStatus.COMPLETED)
    )

    if source_ids:
        base_stmt = base_stmt.where(DocumentChunk.document_id.in_(source_ids))

    reference_rows: list = []
    for ref in ref_targets:
        stmt = base_stmt.where(
            DocumentChunk.chunk_metadata.op("->>")("article") == ref["article"]
        )

        if ref.get("clause"):
            stmt = stmt.where(
                DocumentChunk.chunk_metadata.op("->>")("clause") == ref["clause"]
            )

        rows = list(db.execute(stmt).all())
        for row in rows:
            if row[0].id not in existing_ids:
                reference_rows.append(row)
                existing_ids.add(row[0].id)

    return reference_rows

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
