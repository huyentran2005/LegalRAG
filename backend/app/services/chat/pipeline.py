from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.chat.classifier import QuestionType, classify_question_type
from app.services.chat.citations import _expand_with_reference
from app.services.chat.information_extraction import build_structured_query_context, extract_structured_query
from app.services.chat.rewrite import _rewrite_query_with_history
from rag.service.answer_parser import OfficeRAG
from rag.service.emb_model import _env_int, embed, embed_batched
from app.services.chat.utils import  _is_ollama_provider
from rag.service.llm_model import get_llm
from app.services.chat.history import _load_conversation_memory
from app.models.chat_session import ChatSession
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.chat.retrieval import  search_similar_chunks, _trim_chunk_content


DEFAULT_CHUNK_CHAR_LIMIT = 900
DEFAULT_OLLAMA_RESULT_LIMIT = 5
DEFAULT_RESULT_LIMIT = 12
DEFAULT_MULTI_ASPECT_RESULT_LIMIT = 16
DEFAULT_ASPECT_LIMIT = 4
DEFAULT_EXTRACTED_RETRIEVAL_WORKERS = 4
DEFAULT_SIBLING_WINDOW = 2
DEFAULT_DIVERSITY_PER_ARTICLE = 3
RETRIEVAL_RRF_K = 60


def _search_with_query(
    db: Session,
    query: str,
    current_user_id: int,
    result_limit: int,
    source_ids: list[int] | None,
) -> list:
    query_embedding = embed([query])[0].tolist()
    return search_similar_chunks(
        db=db,
        query=query,
        query_embedding=query_embedding,
        owner_id=current_user_id,
        k=result_limit,
        source_ids=source_ids,
    )


def _structured_retrieval_queries(structured_query: dict, fallback_question: str) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()

    def add_query(value) -> None:
        query = re.sub(r"\s+", " ", str(value or "")).strip()
        key = query.lower()
        if query and key not in seen:
            queries.append(query)
            seen.add(key)

    expanded_queries = structured_query.get("expanded_queries")
    if isinstance(expanded_queries, list):
        for query in expanded_queries:
            add_query(query)

    for aspect in structured_query.get("aspects", []):
        if not isinstance(aspect, dict):
            continue
        add_query(aspect.get("question"))
        add_query(aspect.get("evidence_need"))

    add_query(structured_query.get("normalized_question") or fallback_question)
    add_query(fallback_question)

    return queries


def _search_extracted_queries_parallel(
    queries: list[str],
    current_user_id: int,
    result_limit: int,
    source_ids: list[int] | None,
) -> list:
    if not queries:
        return []

    worker_count = min(
        max(1, _env_int("EXTRACTED_RETRIEVAL_WORKERS", DEFAULT_EXTRACTED_RETRIEVAL_WORKERS)),
        len(queries),
    )
    embeddings = embed_batched(queries)

    def search_one(index: int) -> tuple[int, list]:
        db = SessionLocal()
        try:
            return index, search_similar_chunks(
                db=db,
                query=queries[index],
                query_embedding=embeddings[index].tolist(),
                owner_id=current_user_id,
                k=result_limit,
                source_ids=source_ids,
            )
        finally:
            db.close()

    ranked_by_query: dict[int, list] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(search_one, index) for index in range(len(queries))]
        for future in as_completed(futures):
            index, rows = future.result()
            ranked_by_query[index] = rows

    fused: dict[int, dict] = {}
    for query_index in range(len(queries)):
        rows = ranked_by_query.get(query_index, [])
        for rank, row in enumerate(rows, start=1):
            chunk = row[0]
            fused.setdefault(chunk.id, {"row": row, "score": 0.0})
            fused[chunk.id]["score"] += 1.0 / (RETRIEVAL_RRF_K + rank)

    ranked = sorted(fused.values(), key=lambda item: item["score"], reverse=True)
    return [item["row"] for item in ranked[:result_limit]]


def _expand_with_siblings(
    db: Session,
    results: list,
    owner_id: int,
    source_ids: list[int] | None,
    window: int | None = None,
) -> list:
    if not results:
        return []

    if window is None:
        window = _env_int("SIBLING_EXPANSION_WINDOW", DEFAULT_SIBLING_WINDOW)
    if window <= 0:
        return []

    existing_ids = {row[0].id for row in results}
    sibling_rows = []
    for chunk, _document in results:
        if chunk.chunk_index is None:
            continue

        stmt = (
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(Document.owner_id == owner_id)
            .where(Document.status == DocumentStatus.COMPLETED)
            .where(DocumentChunk.document_id == chunk.document_id)
            .where(DocumentChunk.chunk_index >= chunk.chunk_index - window)
            .where(DocumentChunk.chunk_index <= chunk.chunk_index + window)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        if source_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(source_ids))

        for row in db.execute(stmt).all():
            sibling = row[0]
            if sibling.id in existing_ids:
                continue
            sibling_rows.append(row)
            existing_ids.add(sibling.id)

    return sibling_rows


def _diversity_rerank(rows: list, limit: int, max_per_article: int | None = None) -> list:
    if max_per_article is None:
        max_per_article = _env_int("DIVERSITY_PER_ARTICLE", DEFAULT_DIVERSITY_PER_ARTICLE)
    if max_per_article <= 0:
        return rows[:limit]

    selected = []
    overflow = []
    counts: dict[tuple, int] = {}
    seen = set()

    for row in rows:
        chunk, document = row
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        metadata = chunk.chunk_metadata or {}
        article_key = (document.id, metadata.get("article"))
        if counts.get(article_key, 0) < max_per_article:
            selected.append(row)
            counts[article_key] = counts.get(article_key, 0) + 1
        else:
            overflow.append(row)

    return (selected + overflow)[:limit]


def _structured_retrieval_text(structured_query: dict, fallback_question: str) -> str:
    parts = [
        str(structured_query.get("normalized_question") or fallback_question),
        fallback_question,
    ]
    for key in ("entities", "constraints"):
        values = structured_query.get(key)
        if isinstance(values, list):
            parts.extend(str(value) for value in values if value)
    for aspect in structured_query.get("aspects", []):
        if not isinstance(aspect, dict):
            continue
        parts.append(str(aspect.get("question") or ""))
        parts.append(str(aspect.get("evidence_need") or ""))
        for key in ("entities", "constraints"):
            values = aspect.get(key)
            if isinstance(values, list):
                parts.extend(str(value) for value in values if value)
    return " ".join(part.strip() for part in parts if part and part.strip())


def _run_retrieval_qa_tool(
    db: Session,
    current_user_id: int,
    question: str,
    retrieval_question: str,
    source_ids: list[int] | None,
    provider: str,
    rag: OfficeRAG,
    llm,
    was_rewritten: bool = False,
    max_aspects: int = 1,
    result_limit_override: int | None = None,
) -> tuple[dict, list, dict[int, tuple], str]:
    structured_query = extract_structured_query(llm, retrieval_question, max_aspects=max_aspects)
    structured_retrieval_question = _structured_retrieval_text(structured_query, retrieval_question)
    extracted_queries = _structured_retrieval_queries(structured_query, retrieval_question)
    if result_limit_override is not None:
        result_limit = result_limit_override
    elif _is_ollama_provider(provider):
        result_limit = _env_int("OLLAMA_RESULT_LIMIT", DEFAULT_OLLAMA_RESULT_LIMIT)
    else:
        result_limit = DEFAULT_RESULT_LIMIT

    results = _search_extracted_queries_parallel(
        queries=extracted_queries,
        current_user_id=current_user_id,
        result_limit=result_limit,
        source_ids=source_ids,
    )

    if not results:
        results = _search_with_query(
            db=db,
            query=structured_retrieval_question,
            current_user_id=current_user_id,
            result_limit=result_limit,
            source_ids=source_ids,
        )

    if not results and (was_rewritten or retrieval_question != question):
        results = _search_with_query(
            db=db,
            query=question,
            current_user_id=current_user_id,
            result_limit=result_limit,
            source_ids=source_ids,
        )
        retrieval_question = question
        structured_query = extract_structured_query(llm, retrieval_question, max_aspects=max_aspects)

    if not results:
        raise HTTPException(status_code=404, detail="No documents found for query")

    expanded_results = (
        results
        + _expand_with_reference(db, results, current_user_id, source_ids=source_ids)
        + _expand_with_siblings(db, results, current_user_id, source_ids=source_ids)
    )
    results = _diversity_rerank(expanded_results, result_limit)

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
    context = build_structured_query_context(structured_query) + "\n\n[TÀI LIỆU GỐC]\n" + "\n".join(numbered_chunks)

    ans = rag.answer(context, retrieval_question, [])
    return ans, results, chunk_lookup, retrieval_question


def _run_normal_qa_tool(
    db: Session,
    current_user_id: int,
    question: str,
    source_ids: list[int] | None,
    provider: str,
    rag: OfficeRAG,
    llm,
) -> tuple[dict, list, dict[int, tuple], str]:
    return _run_retrieval_qa_tool(
        db=db,
        current_user_id=current_user_id,
        question=question,
        retrieval_question=question,
        source_ids=source_ids,
        provider=provider,
        rag=rag,
        llm=llm,
        max_aspects=_env_int("ASPECT_LIMIT", DEFAULT_ASPECT_LIMIT),
    )


def _run_context_dependent_qa_tool(
    db: Session,
    current_user_id: int,
    question: str,
    source_ids: list[int] | None,
    provider: str,
    llm,
    rag: OfficeRAG,
    history: list[dict],
) -> tuple[dict, list, dict[int, tuple], str]:
    retrieval_question = _rewrite_query_with_history(llm, history, question)
    return _run_retrieval_qa_tool(
        db=db,
        current_user_id=current_user_id,
        question=question,
        retrieval_question=retrieval_question,
        source_ids=source_ids,
        provider=provider,
        rag=rag,
        llm=llm,
        was_rewritten=retrieval_question != question,
        max_aspects=_env_int("ASPECT_LIMIT", DEFAULT_ASPECT_LIMIT),
    )


def _run_rag_pipeline(
    db: Session,
    session: ChatSession,
    current_user_id: int,
    question: str,
    source_ids: list[int] | None,
    provider: str,
    gemini_api_key: str | None = None,
) -> tuple[dict, list, dict[int, tuple], str]:
    llm = get_llm(provider, gemini_api_key=gemini_api_key)
    rag = OfficeRAG(llm)
    history = _load_conversation_memory(db, session.id, current_user_id)
    question_type = classify_question_type(llm, history, question)

    if question_type == QuestionType.CONTEXT_DEPENDENT_QA:
        return _run_context_dependent_qa_tool(
            db=db,
            current_user_id=current_user_id,
            question=question,
            source_ids=source_ids,
            provider=provider,
            llm=llm,
            rag=rag,
            history=history,
        )

    if question_type == QuestionType.MULTI_ASPECT_QA:
        return _run_retrieval_qa_tool(
            db=db,
            current_user_id=current_user_id,
            question=question,
            retrieval_question=question,
            source_ids=source_ids,
            provider=provider,
            rag=rag,
            llm=llm,
            max_aspects=_env_int("MULTI_ASPECT_LIMIT", 4),
            result_limit_override=_env_int("MULTI_ASPECT_RESULT_LIMIT", DEFAULT_MULTI_ASPECT_RESULT_LIMIT),
        )

    return _run_normal_qa_tool(
        db=db,
        current_user_id=current_user_id,
        question=question,
        source_ids=source_ids,
        provider=provider,
        rag=rag,
        llm=llm,
    )
