from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.chat.rewrite import _contextualize_query
from rag.service.answer_parser import OfficeRAG
from rag.service.emb_model import _env_int, embed
from app.services.chat.utils import  _is_ollama_provider
from rag.service.llm_model import get_llm
from app.services.chat.history import _load_conversation_memory
from app.models.chat_session import ChatSession
from app.services.chat.retrieval import  search_similar_chunks, _trim_chunk_content


DEFAULT_CHUNK_CHAR_LIMIT = 900
DEFAULT_OLLAMA_RESULT_LIMIT = 5

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

