import numpy as np
from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import Text, cast, func, literal, select
import re
import os

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.chat_message import ChatMessage, MessageRole
from app.models.chat_session import ChatSession
from app.schemas.chat import AskRequest, AnswerResponse, SourceOut, ChatMessageOut
from rag.service.answer_parser import OfficeRAG, FocusedAnswerParser
from rag.service.llm_model import get_llm
from rag.service.emb_model import embed

router = APIRouter(prefix="/chat", tags=["chat"])
CITATION_SIMILARITY_THRESHOLD = 0.45
HYBRID_POOL_SIZE = 80
RRF_K = 60
DEFAULT_CHUNK_CHAR_LIMIT = 900
DEFAULT_OLLAMA_RESULT_LIMIT = 5


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _is_ollama_provider(provider: str | None) -> bool:
    return not provider or not provider.startswith("gemini")


def _trim_chunk_content(content: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", content).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rsplit(' ', 1)[0]}..."


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

    fused: dict[int, dict] = {}
    for rank, row in enumerate(vector_rows, start=1):
        chunk = row[0]
        fused.setdefault(chunk.id, {"row": row, "score": 0.0})
        fused[chunk.id]["score"] += 1.0 / (RRF_K + rank)

    for rank, row in enumerate(lexical_rows, start=1):
        chunk = row[0]
        fused.setdefault(chunk.id, {"row": row, "score": 0.0})
        fused[chunk.id]["score"] += 1.0 / (RRF_K + rank)

    ranked = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
    return [item["row"] for item in ranked[:k]]
 
 
def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
 
 
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
 
 
@router.post("/ask", response_model=AnswerResponse)
def ask_question( payload: AskRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not payload.question:
        raise HTTPException(status_code=400, detail="Question is required")
 
    query_embedding = embed([payload.question])[0].tolist()
 
    result_limit = (
        _env_int("OLLAMA_RESULT_LIMIT", DEFAULT_OLLAMA_RESULT_LIMIT)
        if _is_ollama_provider(payload.provider)
        else 8
    )

    results = search_similar_chunks(
        db=db,
        query=payload.question,
        query_embedding=query_embedding,
        owner_id=current_user.id,
        k=result_limit,
        source_ids=payload.sourceIds,
    )
 
    if not results:
        raise HTTPException(status_code=404, detail="No documents found for query")
 
    # Build context có đánh số [đoạn i] + chunk_lookup để gán citation sau này.
    chunk_lookup: dict[int, tuple] = {}
    numbered_chunks = []
    chunk_char_limit = (
        _env_int("OLLAMA_CHUNK_CHAR_LIMIT", DEFAULT_CHUNK_CHAR_LIMIT)
        if _is_ollama_provider(payload.provider)
        else 1600
    )
    for i, (chunk, document) in enumerate(results, start=1):
        chunk_lookup[i] = (document, chunk)
        numbered_chunks.append(f"[đoạn {i}] {_trim_chunk_content(chunk.content, chunk_char_limit)}")
    context = "\n".join(numbered_chunks)
 
    llm = get_llm(payload.provider)
    rag = OfficeRAG(llm)
    try:
        ans = rag.answer(context, payload.question)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "Qwen phản hồi quá lâu nên yêu cầu đã hết thời gian chờ. "
                "Bạn thử hỏi ngắn hơn, chọn ít tài liệu hơn, hoặc tăng OLLAMA_TIMEOUT."
            ),
        ) from exc
    raw_answer = ans["answer"]
    token = ans["token"]
    if FocusedAnswerParser._looks_degenerate(raw_answer):
        # Output bị suy biến (lẫn ký tự lạ ngoài tiếng Việt/Latin) -> không
        # hiển thị rác cho người dùng, trả về thông báo an toàn.
        final_answer = (
            "Xin lỗi, hệ thống gặp lỗi khi tạo câu trả lời cho câu hỏi này. "
            "Vui lòng thử lại hoặc diễn đạt câu hỏi theo cách khác."
        )
        citations = {}
        used_sources = []
        parts = [{"text": final_answer}]
    elif "không có thông tin" in raw_answer.lower():
        final_answer = "Không có thông tin nào."
        citations = {}
        used_sources = []
        parts = [{"text": final_answer}]
    else:
        sentences = FocusedAnswerParser.split_sentences(raw_answer)
        assigned = _assign_citations_by_similarity(sentences, chunk_lookup)
 
        final_answer = " ".join(s for s, _, _ in assigned) or raw_answer
 
        # Build citations CHỈ từ chunk thực sự khớp (similarity >= ngưỡng)
        used_chunk_indices = sorted({idx for _, idx, _ in assigned if idx is not None})
        citations = {}
        citation_document_ids = set()
        used_sources = []
        for idx in used_chunk_indices:
            document, chunk = chunk_lookup[idx]
            citations[idx] = {
                "sourceId": document.id,
                "sourceName": document.filename,
                "page": f"Trang {(chunk.chunk_index or 0) + 1}",
                "excerpt": chunk.content.strip()[:500],
            }
            if document.id not in citation_document_ids:
                citation_document_ids.add(document.id)
                used_sources.append(document.id)
 
        parts = [{"text": final_answer}]
        for idx in used_chunk_indices:
            parts.append({"cite": str(idx)})
 
        # Nếu không câu nào đạt ngưỡng similarity với bất kỳ chunk nào,
        # cảnh báo rõ ràng thay vì âm thầm hiển thị answer không có nguồn.
        if not used_chunk_indices:
            final_answer += (
                " (Lưu ý: hệ thống không xác định được nguồn tài liệu chắc chắn cho câu trả lời này, "
                "vui lòng kiểm tra lại thủ công.)"
            )
            parts = [{"text": final_answer}]
 
    session = None
    if payload.sessionId:
        session = db.get(ChatSession, payload.sessionId)
        if not session or session.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Chat session not found")
    else:
        session = ChatSession(
            user_id=current_user.id,
            title=payload.question[:255],
        )
        db.add(session)
        db.flush()
 
    db.add(ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=payload.question,
        token = 0,
    ))
    db.add(ChatMessage(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=final_answer,
        citations={
            "parts": parts,
            "citations": citations,
            "usedSources": used_sources,
        },
        token = token,
    ))
    db.commit()
 
    cited_documents = (
        {chunk_lookup[i][0].id: chunk_lookup[i][0] for i in citations.keys()}
        if citations else {document.id: document for _, document in results}
    )
    source_documents = [SourceOut.model_validate(doc) for doc in cited_documents.values()]
 
    return AnswerResponse(
        sessionId=session.id,
        answer=final_answer,
        sources=source_documents,
        citations=citations,  # type: ignore
        parts=parts,  # type: ignore
        usedSources=used_sources,
        token = token,
    )


@router.get("/messages", response_model = list[ChatMessageOut])
def get_all_messages(db : Session = Depends(get_db), current_user = Depends(get_current_user)):

    messages = (
        db.query(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    result: list[ChatMessageOut] = []
    for msg in messages:
        if msg.role == MessageRole.USER:
            result.append(
                ChatMessageOut(
                    id=msg.id,
                    sessionId=msg.session_id,
                    role="user",
                    text=msg.content,
                    parts=None,
                    citations=None,
                    usedSources=None,
                    createdAt=msg.created_at,
                    token =0,
                )
            )
        else:  # ASSISTANT
            stored = msg.citations or {}
            result.append(
                ChatMessageOut(
                    id=msg.id,
                    sessionId=msg.session_id,
                    role="assistant",
                    text=msg.content,
                    parts=stored.get("parts", [{"text": msg.content}]), # type: ignore
                    citations=stored.get("citations", {}), # type: ignore
                    usedSources=stored.get("usedSources", []), # type: ignore
                    createdAt=msg.created_at,
                    token = msg.token,
                ) 
            )

    return result
