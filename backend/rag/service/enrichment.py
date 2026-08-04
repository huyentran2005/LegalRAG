"""Sinh metadata chắc chắn cho từng chunk, không dùng LLM."""
from rag.service.parser import VietnameseLegalParser


def _remove_self_references(references: list[dict], metadata: dict) -> list[dict]:
    current_article = metadata.get("article")
    current_clauses = set(metadata.get("clauses", []))
    if metadata.get("clause"):
        current_clauses.add(metadata["clause"])

    filtered = []
    seen = set()
    for ref in references:
        article = ref.get("article")
        clause = ref.get("clause")
        if article == current_article and (not clause or not current_clauses or clause in current_clauses):
            continue
        key = (article, clause)
        if key not in seen:
            filtered.append(ref)
            seen.add(key)
    return filtered


def _title_from_chunk(content: str, metadata: dict) -> str:
    if metadata.get("article_title"):
        return str(metadata["article_title"])
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return first_line[:120] or str(metadata.get("article", "Đoạn văn bản pháp luật"))


def enrich_chunk_metadata(content: str, metadata: dict) -> dict:
    """Chỉ giữ phần metadata chắc chắn, không sinh metadata bằng LLM."""
    parser = VietnameseLegalParser(law_name=str(metadata.get("law", "")))
    title = _title_from_chunk(content, metadata)

    semantic = {
        "title": title,
        "references": _remove_self_references(parser.find_references(content), metadata),
    }
    return {**metadata, **semantic}
