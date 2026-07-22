import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.chat_message import ChatMessage, MessageRole
from app.models.chat_session import ChatSession
from app.schemas.chat import AskRequest, AnswerResponse, SourceOut
from rag.service.answer_parser import OfficeRAG, FocusedAnswerParser

router = APIRouter(prefix="/chat", tags=["chat"])

# Ngưỡng cosine similarity để coi 1 câu trả lời là "grounded" vào 1 chunk cụ thể.
# Nếu similarity thấp hơn ngưỡng này, câu đó KHÔNG được gán citation
# (an toàn hơn là gán bừa vào chunk không thực sự liên quan).
SIMILARITY_THRESHOLD = 0.35


import re


def _extract_numbers(text: str) -> set[str]:
    """Lấy các con số xuất hiện trong text (vd '175', '14', '1.5') để so khớp
    với chunk gốc — số liệu là phần quan trọng nhất trong văn bản pháp luật,
    và cosine similarity không đủ nhạy để phát hiện số bị sai/hallucinate."""
    return set(re.findall(r'\d+(?:[.,]\d+)?', text))


def _numbers_supported(sentence: str, chunk_text: str) -> bool:
    """Kiểm tra mọi con số trong câu trả lời có thực sự xuất hiện trong chunk gốc.
    Nếu câu không chứa số nào -> coi như không cần kiểm tra (trả về True).
    Nếu câu có số nhưng chunk không chứa số đó -> khả năng cao là hallucinate
    số liệu, dù chủ đề/embedding có vẻ giống nhau."""
    sentence_numbers = _extract_numbers(sentence)
    if not sentence_numbers:
        return True
    chunk_numbers = _extract_numbers(chunk_text)
    return sentence_numbers.issubset(chunk_numbers)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _assign_citations_by_similarity(
    sentences: list[str],
    chunk_lookup: dict[int, tuple],
    query_encoder,
) -> list[tuple[str, int | None, float]]:
    """
    Với mỗi câu trong answer, tìm chunk (trong kết quả retrieval) có embedding
    gần nhất về mặt ngữ nghĩa, dùng CÙNG encoder đã dùng để encode câu hỏi.

    Trả về list (sentence_text, best_chunk_index_or_None, similarity_score).
    """
    if not sentences:
        return []

    chunk_indices = list(chunk_lookup.keys())
    # Encode lại nội dung chunk bằng encoder hiện có, để đảm bảo cùng không gian vector
    # với câu trả lời (an toàn hơn dùng lại embedding cũ trong DB, vốn có thể lệch
    # model nếu embedding ingestion và encoder hiện tại không khớp phiên bản).
    chunk_texts = [chunk_lookup[i][1].content.strip() for i in chunk_indices]
    chunk_embeddings = query_encoder.encode(chunk_texts, show_progress_bar=False)

    sentence_embeddings = query_encoder.encode(sentences, show_progress_bar=False)

    results = []
    for sent_text, sent_emb in zip(sentences, sentence_embeddings):
        # Xếp hạng các chunk theo similarity giảm dần, rồi duyệt từ cao xuống thấp,
        # chỉ chấp nhận chunk đầu tiên vừa đủ ngưỡng similarity VÀ khớp số liệu.
        scored = sorted(
            (
                (idx, _cosine_sim(sent_emb, chunk_emb))
                for idx, chunk_emb in zip(chunk_indices, chunk_embeddings)
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )

        best_idx = None
        best_score = 0.0
        for idx, score in scored:
            if score < SIMILARITY_THRESHOLD:
                break  # đã sắp xếp giảm dần, dưới ngưỡng thì các chunk sau càng thấp hơn
            chunk_text = chunk_lookup[idx][1].content
            if _numbers_supported(sent_text, chunk_text):
                best_idx, best_score = idx, score
                break
            # Similarity cao nhưng số liệu không khớp -> khả năng hallucinate số,
            # bỏ qua chunk này, thử chunk có similarity thấp hơn kế tiếp.

        if best_idx is not None:
            results.append((sent_text, best_idx, best_score))
        else:
            # Không tìm được chunk nào vừa đủ similarity vừa khớp số liệu.
            results.append((sent_text, None, 0.0))
    return results


@router.post("/ask", response_model=AnswerResponse)
def ask_question(request: Request, payload: AskRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not payload.question:
        raise HTTPException(status_code=400, detail="Question is required")

    query_encoder = request.app.state.seq
    query_embedding = query_encoder.encode([payload.question], show_progress_bar=False)[0].tolist()

    query_stmt = (
        select(DocumentChunk, Document)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.owner_id == current_user.id)
        .where(Document.status == DocumentStatus.COMPLETED)
    )
    if payload.sourceIds:
        query_stmt = query_stmt.where(DocumentChunk.document_id.in_(payload.sourceIds))

    query_stmt = query_stmt.order_by(DocumentChunk.embedding.cosine_distance(query_embedding)).limit(5)
    results = db.execute(query_stmt).all()

    if not results:
        raise HTTPException(status_code=404, detail="No documents found for query")

    # Đánh số chunk theo thứ tự retrieval (dùng để tra cứu khi gán citation sau này)
    chunk_lookup: dict[int, tuple] = {}
    numbered_chunks = []
    for i, (chunk, document) in enumerate(results, start=1):
        chunk_lookup[i] = (document, chunk)
        numbered_chunks.append(f"[đoạn {i}] {chunk.content.strip()}")

    context = "\n".join(numbered_chunks)

    llm = request.app.state.llm
    rag = OfficeRAG(llm)
    raw_answer = rag.answer(context, payload.question)

    if FocusedAnswerParser._looks_degenerate(raw_answer):
        # Output bị suy biến (lẫn ký tự lạ ngoài tiếng Việt/Latin) -> không hiển thị
        # rác cho người dùng, trả về thông báo an toàn thay vì cố parse tiếp.
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
        assigned = _assign_citations_by_similarity(sentences, chunk_lookup, query_encoder)

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
        if citations else {doc.id: doc for _, doc in results}
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