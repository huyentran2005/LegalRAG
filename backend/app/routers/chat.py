import numpy as np
from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import Text, and_, desc, func
import logging

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document
from app.models.chat_message import ChatMessage, MessageRole
from app.models.chat_session import ChatSession
from app.schemas.chat import AskRequest, AnswerResponse, SourceOut, ChatMessageOut, _session_payload, _message_out
from app.schemas.sessions import CreateSessionRequest
from app.services.chat.utils import _fallback_provider,_is_quota_exhausted_error
from app.services.chat.citations import _assign_citations_by_similarity
from rag.service.answer_parser import  FocusedAnswerParser
from app.services.chat.pipeline import _run_rag_pipeline



router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)





@router.post("/sessions")
def create_chat_session(payload: CreateSessionRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    session = ChatSession(user_id=current_user.id, title=payload.title or "Cuộc chat mới")
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_payload(session)


@router.get("/sessions")
def get_chat_sessions(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = (
        db.query(ChatSession, func.count(Document.id).label("document_count"))
        .outerjoin(
            Document,
            and_(
                Document.session_id == ChatSession.id,
                Document.owner_id == current_user.id,
            ),
        )
        .filter(ChatSession.user_id == current_user.id)
        .group_by(ChatSession.id)
        .order_by(desc(ChatSession.created_at))
        .all()
    )
    return [_session_payload(session, document_count) for session, document_count in rows]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [_message_out(msg) for msg in messages]
 
@router.post("/ask", response_model=AnswerResponse)
def ask_question( payload: AskRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not payload.question:
        raise HTTPException(status_code=400, detail="Question is required")

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
 
    primary_provider = payload.provider or "gemini-3.5-flash"
    try:
        ans, results, chunk_lookup, retrieval_question = _run_rag_pipeline(
            db=db,
            session=session,
            current_user_id=current_user.id,
            question=payload.question,
            source_ids=payload.sourceIds,
            provider=primary_provider,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "Mô hình phản hồi quá lâu nên yêu cầu đã hết thời gian chờ. "
                "Bạn thử hỏi ngắn hơn, chọn ít tài liệu hơn, hoặc tăng OLLAMA_TIMEOUT."
            ),
        ) from exc
    except Exception as exc:
        if primary_provider.startswith("gemini") and _is_quota_exhausted_error(exc):
            logger.warning("Gemini quota exhausted, falling back to Ollama: %s", exc)
            try:
                ans, results, chunk_lookup, retrieval_question = _run_rag_pipeline(
                    db=db,
                    session=session,
                    current_user_id=current_user.id,
                    question=payload.question,
                    source_ids=payload.sourceIds,
                    provider=_fallback_provider(),
                )
            except httpx.TimeoutException as timeout_exc:
                raise HTTPException(
                    status_code=504,
                    detail=(
                        "Ollama phản hồi quá lâu nên yêu cầu đã hết thời gian chờ. "
                        "Bạn thử hỏi ngắn hơn, chọn ít tài liệu hơn, hoặc tăng OLLAMA_TIMEOUT."
                    ),
                ) from timeout_exc
            except Exception as fallback_exc:
                logger.exception("Gemini quota exhausted and fallback failed")
                raise HTTPException(
                    status_code=503,
                    detail=f"Gemini đang hết quota và fallback sang Ollama cũng thất bại: {fallback_exc}",
                ) from fallback_exc
        else:
            logger.exception("Failed to generate chat answer")
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Không gọi được mô hình sinh câu trả lời: {exc}. "
                    "Kiểm tra provider, API key/model name hoặc Ollama service."
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
    if payload.sourceIds:
        (
            db.query(Document)
            .filter(Document.owner_id == current_user.id)
            .filter(Document.id.in_(payload.sourceIds))
            .filter(Document.session_id.is_(None))
            .update({Document.session_id: session.id}, synchronize_session=False)
        )
 
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
        result.append(_message_out(msg))

    return result
