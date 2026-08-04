import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
import re
import json

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


_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-Ỵà-ỵĐđ]+")


def _search_tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text) if len(token) > 1]


def _metadata_text(metadata: dict | None) -> str:
    if not metadata:
        return ""
    return json.dumps(metadata, ensure_ascii=False)


def _lexical_score(query: str, chunk: DocumentChunk) -> float:
    query_tokens = _search_tokens(query)
    if not query_tokens:
        return 0.0

    searchable = f"{chunk.content} {_metadata_text(chunk.chunk_metadata)}".lower()
    score = 0.0
    for token in query_tokens:
        occurrences = searchable.count(token)
        if occurrences:
            score += 1.0 + min(occurrences, 5) * 0.2

    phrase = query.strip().lower()
    if phrase and phrase in searchable:
        score += 3.0
    return score
 
 
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

    candidate_rows = list(db.execute(base_stmt.limit(1000)).all())
    lexical_rows = sorted(
        ((row, _lexical_score(query, row[0])) for row in candidate_rows),
        key=lambda item: item[1],
        reverse=True,
    )
    lexical_rows = [row for row, score in lexical_rows[:HYBRID_POOL_SIZE] if score > 0]

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
 
    results = search_similar_chunks(
        db=db,
        query=payload.question,
        query_embedding=query_embedding,
        owner_id=current_user.id,
        k=8,
        source_ids=payload.sourceIds,
    )
 
    if not results:
        raise HTTPException(status_code=404, detail="No documents found for query")
 
    # Build context có đánh số [đoạn i] + chunk_lookup để gán citation sau này.
    chunk_lookup: dict[int, tuple] = {}
    numbered_chunks = []
    for i, (chunk, document) in enumerate(results, start=1):
        chunk_lookup[i] = (document, chunk)
        numbered_chunks.append(f"[đoạn {i}] {chunk.content.strip()}")
    context = "\n".join(numbered_chunks)
 
    llm = get_llm(payload.provider)
    rag = OfficeRAG(llm)
    raw_answer = rag.answer(context, payload.question)
 
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
                ) 
            )

    return result
