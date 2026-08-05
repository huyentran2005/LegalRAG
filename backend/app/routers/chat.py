import numpy as np
from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import Text, and_, cast, desc, func, literal, or_, select
import re
import os
import unicodedata
import logging

from app.api.deps import get_current_user
from app.database import get_db
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.chat_message import ChatMessage, MessageRole
from app.models.chat_session import ChatSession
from app.schemas.chat import AskRequest, AnswerResponse, SourceOut, ChatMessageOut
from app.schemas.sessions import CreateSessionRequest
from rag.service.answer_parser import OfficeRAG, FocusedAnswerParser
from rag.service.llm_model import get_llm
from rag.service.emb_model import embed

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
CITATION_SIMILARITY_THRESHOLD = 0.45
HYBRID_POOL_SIZE = 80
RRF_K = 60
PHRASE_POOL_SIZE = 40
DEFAULT_CHUNK_CHAR_LIMIT = 900
DEFAULT_OLLAMA_RESULT_LIMIT = 5
MAX_REFERENCE_CHUNKS = 10
MAX_HISTORY_TURNS = 10
REFERENCE_RULE_PATTERN = re.compile(
    r"\b("
    r"khoản này|điều này|điều đó|cái này|cái đó|việc này|việc đó|"
    r"nội dung này|quy định này|trường hợp này|vấn đề này|"
    r"nó|họ|người đó|bên đó|"
    r"tiếp theo|tiếp tục|vậy còn|thế còn|còn khoản|còn điều|"
    r"như trên|ở trên|vừa nêu|vừa nói|vừa rồi|trước đó|"
    r"câu trên|ý trên|phần trên|tài liệu đó"
    r")\b",
    re.IGNORECASE,
)

QUERY_STOPWORDS = {
    "anh", "chị", "em", "tôi", "mình", "bạn", "cho", "hỏi", "hỏi",
    "về", "và", "hoặc", "là", "có", "không", "được", "bị", "thì",
    "như", "nào", "gì", "ra", "sao", "theo", "trong", "của", "các",
    "những", "người", "giữa", "một", "này", "đó", "ở", "tại",
}



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


def _load_conversation_memory(
        db: Session,
        session_id,
        owner_id: int,
        max_turns: int = MAX_HISTORY_TURNS,
) -> list[dict]:
    """
    Lay N luot hoi thoai gan nhat cua session, dung lam "tri nho" ngan han
    cho cau hoi tiep theo. JOIN qua ChatSession de xac nhan session thuoc
    dung owner_id - tranh load nham lich su cua user khac du chi thoang qua.
    """
    if session_id is None:
         return []

    rows= (
        db.query(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .filter(ChatMessage.session_id == session_id)
        .filter(ChatSession.user_id == owner_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(max_turns * 2)
        .all()
    )
    rows.reverse()
    return [{"role": msg.role.value, "content": msg.content} for msg in rows]

def _question_matches_reference_rule(question: str) -> bool:
    return bool(REFERENCE_RULE_PATTERN.search(question.lower()))


def _format_memory_for_prompt(memory: list[dict]) -> str:
    lines = []
    for turn in memory:
        speaker = "Người dùng" if turn.get("role") == "user" else "Trợ lý"
        content = re.sub(r"\s+", " ", turn.get("content", "")).strip()
        if content:
            lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _llm_text(raw) -> str:
    return OfficeRAG._extract_text(raw).strip()


def _is_quota_exhausted_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "resource_exhausted" in text or "quota exceeded" in text or "429" in text


def _fallback_provider() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def _run_rag_pipeline(
    db: Session,
    session: ChatSession,
    current_user_id: int,
    question: str,
    source_ids: list[int] | None,
    provider: str,
) -> tuple[dict, list, dict[int, tuple], str]:
    llm = get_llm(provider)
    rag = OfficeRAG(llm)
    history = _load_conversation_memory(db, session.id, current_user_id)
    retrieval_question, was_rewritten = _contextualize_query(llm, history, question)

    query_embedding = embed([retrieval_question])[0].tolist()
    result_limit = (
        _env_int("OLLAMA_RESULT_LIMIT", DEFAULT_OLLAMA_RESULT_LIMIT)
        if _is_ollama_provider(provider)
        else 8
    )

    results = search_similar_chunks(
        db=db,
        query=retrieval_question,
        query_embedding=query_embedding,
        owner_id=current_user_id,
        k=result_limit,
        source_ids=source_ids,
    )

    if not results and was_rewritten:
        original_embedding = embed([question])[0].tolist()
        results = search_similar_chunks(
            db=db,
            query=question,
            query_embedding=original_embedding,
            owner_id=current_user_id,
            k=result_limit,
            source_ids=source_ids,
        )
        retrieval_question = question

    if not results:
        raise HTTPException(status_code=404, detail="No documents found for query")

    chunk_lookup: dict[int, tuple] = {}
    numbered_chunks = []
    chunk_char_limit = (
        _env_int("OLLAMA_CHUNK_CHAR_LIMIT", DEFAULT_CHUNK_CHAR_LIMIT)
        if _is_ollama_provider(provider)
        else 1600
    )
    for i, (chunk, document) in enumerate(results, start=1):
        chunk_lookup[i] = (document, chunk)
        numbered_chunks.append(f"[đoạn {i}] {_trim_chunk_content(chunk.content, chunk_char_limit)}")
    context = "\n".join(numbered_chunks)

    ans = rag.answer(context, retrieval_question, [])
    return ans, results, chunk_lookup, retrieval_question


def _classify_needs_history(llm, memory: list[dict], current_question: str) -> bool:
    if not memory:
        return False
    prompt = f"""
Bạn là bộ phân loại truy vấn. Trả lời duy nhất YES hoặc NO.

Cần dùng lịch sử hội thoại nếu câu hỏi hiện tại phụ thuộc vào nội dung trước đó
để hiểu đúng đối tượng, điều, khoản, chủ thể, hoặc phạm vi. Nếu câu hỏi tự đủ
nghĩa để tìm kiếm tài liệu thì trả lời NO.

[LỊCH SỬ]:
{_format_memory_for_prompt(memory)}

[CÂU HỎI HIỆN TẠI]:
{current_question}

YES/NO:
""".strip()
    try:
        text = _llm_text(llm.invoke(prompt)).upper()
    except Exception:
        return False
    return text.startswith("YES") or "YES" in text[:12]


def _rewrite_query_with_history(llm, memory: list[dict], current_question: str) -> str:
    prompt = f"""
Viết lại câu hỏi hiện tại thành một câu hỏi độc lập, đầy đủ ngữ cảnh để truy vấn
tài liệu pháp luật. Chỉ trả về đúng câu hỏi đã viết lại, không giải thích.
Giữ nguyên ngôn ngữ tiếng Việt và không thêm thông tin không có trong lịch sử.

[LỊCH SỬ]:
{_format_memory_for_prompt(memory)}

[CÂU HỎI HIỆN TẠI]:
{current_question}

[CÂU HỎI ĐỘC LẬP]:
""".strip()
    try:
        rewritten = _llm_text(llm.invoke(prompt))
    except Exception:
        return current_question

    rewritten = re.sub(r"^\s*\[?CÂU HỎI ĐỘC LẬP\]?:\s*", "", rewritten, flags=re.IGNORECASE).strip()
    rewritten = rewritten.strip("\"'` ")
    if not rewritten or FocusedAnswerParser._looks_degenerate(rewritten):
        return current_question
    return rewritten


def _contextualize_query(llm, memory: list[dict], current_question: str) -> tuple[str, bool]:
    """
    Neu co lich su hoi thoai, viet lai cau hoi hien tai thanh 1 cau hoi doc
    lap chua du ngu canh, dung de SEARCH (vector + FTS) - KHONG dung cau
    hoi tho neu no phu thuoc ngu canh truoc (VD "Khoan 2 thi sao?" ->
    "Khoan 2 cua Dieu 40 quy dinh gi?"). Khong anh huong cau hoi goc hien
    thi cho user hay luu DB - chi dung noi bo cho buoc search.
    """
    if not memory:
        return current_question, False

    needs_history = _question_matches_reference_rule(current_question)
    if not needs_history:
        needs_history = _classify_needs_history(llm, memory, current_question)

    if not needs_history:
        return current_question, False

    rewritten = _rewrite_query_with_history(llm, memory, current_question)
    return rewritten, rewritten != current_question
def _message_out(msg: ChatMessage) -> ChatMessageOut:
    if msg.role == MessageRole.USER:
        return ChatMessageOut(
            id=msg.id,
            sessionId=msg.session_id,
            role="user",
            text=msg.content,
            parts=None,
            citations=None,
            usedSources=None,
            createdAt=msg.created_at,
            token=0,
        )

    stored = msg.citations or {}
    return ChatMessageOut(
        id=msg.id,
        sessionId=msg.session_id,
        role="assistant",
        text=msg.content,
        parts=stored.get("parts", [{"text": msg.content}]), # type: ignore
        citations=stored.get("citations", {}), # type: ignore
        usedSources=stored.get("usedSources", []), # type: ignore
        createdAt=msg.created_at,
        token=msg.token,
    )


def _session_payload(session: ChatSession, document_count: int = 0) -> dict:
    return {
        "id": session.id,
        "title": session.title,
        "createdAt": session.created_at,
        "documentCount": document_count,
    }


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
