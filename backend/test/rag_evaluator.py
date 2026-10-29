from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


VIETNAMESE_STOPWORDS = {
    "a", "anh", "ban", "bang", "bi", "boi", "cac", "cai", "can", "cau",
    "cho", "co", "con", "cua", "da", "dang", "de", "den", "di", "do",
    "duoc", "duoi", "gi", "hay", "hon", "khi", "khong", "la", "lai",
    "lam", "len", "lien", "ma", "mot", "nao", "nay", "neu", "nguoi",
    "nhung", "nhu", "o", "phai", "qua", "ra", "rang", "sau", "se",
    "tai", "the", "theo", "thi", "trong", "tu", "va", "vao", "ve",
    "vi", "voi",
}


@dataclass
class EvaluationItem:
    question: str
    expected_answer: str
    generated_answer: str
    retrieval_recall_at_10: float
    retrieval_precision_at_10: float
    answer_relevancy: float
    faithfulness: float
    context_relevance: float
    context_recall: float
    context_precision: float
    retrieved_contexts: list[dict[str, Any]]
    token: int = 0


def _strip_accents(text: str) -> str:
    replacements = {
        "àáạảãâầấậẩẫăằắặẳẵ": "a",
        "èéẹẻẽêềếệểễ": "e",
        "ìíịỉĩ": "i",
        "òóọỏõôồốộổỗơờớợởỡ": "o",
        "ùúụủũưừứựửữ": "u",
        "ỳýỵỷỹ": "y",
        "đ": "d",
    }
    lowered = text.lower()
    for chars, replacement in replacements.items():
        lowered = re.sub(f"[{chars}]", replacement, lowered)
    return lowered


def tokenize(text: str) -> list[str]:
    normalized = _strip_accents(text)
    tokens = re.findall(r"[a-z0-9]+", normalized, flags=re.IGNORECASE)
    return [
        token
        for token in tokens
        if len(token) >= 2 and token not in VIETNAMESE_STOPWORDS
    ]


def _token_set(text: str) -> set[str]:
    return set(tokenize(text))


def _coverage(needle: str, haystack: str) -> float:
    needle_tokens = _token_set(needle)
    if not needle_tokens:
        return 0.0
    return len(needle_tokens & _token_set(haystack)) / len(needle_tokens)


def _jaccard(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _chunk_text(context: dict[str, Any]) -> str:
    return str(context.get("content") or context.get("excerpt") or "")


def score_case(
    question: str,
    expected_answer: str,
    generated_answer: str,
    retrieved_contexts: list[dict[str, Any]],
    *,
    k: int = 10,
    relevance_threshold: float = 0.12,
    token: int = 0,
) -> EvaluationItem:
    top_contexts = retrieved_contexts[:k]
    joined_context = "\n".join(_chunk_text(context) for context in top_contexts)
    relevant_flags = [
        _coverage(expected_answer, _chunk_text(context)) >= relevance_threshold
        for context in top_contexts
    ]

    answer_relevancy = (
        0.65 * _coverage(expected_answer, generated_answer)
        + 0.35 * _jaccard(question, generated_answer)
    )
    faithfulness = _coverage(generated_answer, joined_context)
    context_relevance = mean(
        [_jaccard(question, _chunk_text(context)) for context in top_contexts]
    ) if top_contexts else 0.0
    context_recall = _coverage(expected_answer, joined_context)
    context_precision = sum(relevant_flags) / k if k else 0.0

    precision_at_relevant_ranks: list[float] = []
    relevant_seen = 0
    for rank, is_relevant in enumerate(relevant_flags, start=1):
        if is_relevant:
            relevant_seen += 1
            precision_at_relevant_ranks.append(relevant_seen / rank)
    ranked_context_precision = mean(precision_at_relevant_ranks) if precision_at_relevant_ranks else 0.0

    return EvaluationItem(
        question=question,
        expected_answer=expected_answer,
        generated_answer=generated_answer,
        retrieval_recall_at_10=context_recall,
        retrieval_precision_at_10=context_precision,
        answer_relevancy=min(answer_relevancy, 1.0),
        faithfulness=min(faithfulness, 1.0),
        context_relevance=min(context_relevance, 1.0),
        context_recall=min(context_recall, 1.0),
        context_precision=min(ranked_context_precision, 1.0),
        retrieved_contexts=top_contexts,
        token=token,
    )


def load_dataset(path: str | Path) -> list[dict[str, str]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Dataset must be a JSON array.")

    dataset = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Item #{index} must be an object.")
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if not question or not answer:
            raise ValueError(f"Item #{index} must include non-empty question and answer.")
        dataset.append({"question": question, "answer": answer})
    return dataset


def summarize(items: list[EvaluationItem]) -> dict[str, Any]:
    metric_names = [
        "retrieval_recall_at_10",
        "retrieval_precision_at_10",
        "answer_relevancy",
        "faithfulness",
        "context_relevance",
        "context_recall",
        "context_precision",
    ]
    return {
        "count": len(items),
        "metrics": {
            name: round(mean([getattr(item, name) for item in items]), 4)
            if items else 0.0
            for name in metric_names
        },
        "items": [asdict(item) for item in items],
    }


def _contexts_from_pipeline_results(results: list) -> list[dict[str, Any]]:
    contexts = []
    for rank, row in enumerate(results, start=1):
        chunk, document = row
        contexts.append(
            {
                "rank": rank,
                "chunk_id": getattr(chunk, "id", None),
                "document_id": getattr(document, "id", None),
                "source_name": getattr(document, "filename", None),
                "chunk_index": getattr(chunk, "chunk_index", None),
                "content": getattr(chunk, "content", "") or "",
            }
        )
    return contexts


def evaluate_with_pipeline(
    dataset_path: str | Path,
    *,
    user_id: int,
    provider: str,
    source_ids: list[int] | None = None,
) -> dict[str, Any]:
    from app.database import SessionLocal
    from app.models.chat_session import ChatSession
    from app.services.chat.citations import (
        _extract_llm_used_citation_indices,
        _format_answer_layout,
        _strip_llm_citation_markers,
    )
    from app.services.chat.pipeline import _run_rag_pipeline

    dataset = load_dataset(dataset_path)
    db = SessionLocal()
    items: list[EvaluationItem] = []
    try:
        session = ChatSession(user_id=user_id, title="RAG evaluation")
        db.add(session)
        db.flush()

        for sample in dataset:
            ans, results, chunk_lookup, _retrieval_question = _run_rag_pipeline(
                db=db,
                session=session,
                current_user_id=user_id,
                question=sample["question"],
                source_ids=source_ids,
                provider=provider,
            )
            raw_answer = ans.get("answer", "")
            used_chunk_indices = _extract_llm_used_citation_indices(raw_answer, chunk_lookup)
            final_answer = _format_answer_layout(_strip_llm_citation_markers(raw_answer) or raw_answer)
            contexts = _contexts_from_pipeline_results(results[:10])
            for context in contexts:
                context["used_in_answer"] = context["rank"] in used_chunk_indices

            items.append(
                score_case(
                    question=sample["question"],
                    expected_answer=sample["answer"],
                    generated_answer=final_answer,
                    retrieved_contexts=contexts,
                    token=int(ans.get("token") or 0),
                )
            )
    finally:
        db.rollback()
        db.close()

    return summarize(items)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate LegalRAG with a JSON golden-answer file.")
    parser.add_argument("--dataset", required=True, help="Path to JSON file: [{\"question\": ..., \"answer\": ...}]")
    parser.add_argument("--user-id", required=True, type=int, help="Owner user id used to retrieve documents.")
    parser.add_argument("--provider", default="gemini-3.6-flash", help="LLM provider used by the existing pipeline.")
    parser.add_argument("--source-ids", default="", help="Optional comma-separated document ids.")
    parser.add_argument("--output", default="", help="Optional output JSON report path.")
    args = parser.parse_args()

    source_ids = [
        int(value.strip())
        for value in args.source_ids.split(",")
        if value.strip()
    ] or None
    report = evaluate_with_pipeline(
        args.dataset,
        user_id=args.user_id,
        provider=args.provider,
        source_ids=source_ids,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
