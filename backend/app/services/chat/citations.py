import re
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk


MAX_REFERENCE_CHUNKS = 10
CITATION_BLOCK_RE = re.compile(r"\[([^\]]*(?:đoạn|doan)[^\]]*)\]", flags=re.IGNORECASE)


def _extract_llm_used_citation_indices(
    answer: str,
    chunk_lookup: dict[int, tuple],
) -> list[int]:
    """Lay citation indices do LLM tu khai bao trong answer, dang [doan n]."""
    if not answer or not chunk_lookup:
        return []

    used_indices = []
    seen = set()
    for match in CITATION_BLOCK_RE.finditer(answer):
        for raw_idx in re.findall(r"\d+", match.group(1)):
            idx = int(raw_idx)
            if idx in chunk_lookup and idx not in seen:
                used_indices.append(idx)
                seen.add(idx)
    return used_indices


def _strip_llm_citation_markers(answer: str) -> str:
    cleaned = CITATION_BLOCK_RE.sub("", answer)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _format_answer_layout(answer: str) -> str:
    cleaned = re.sub(r"[ \t]+", " ", answer).strip()
    cleaned = re.sub(r"(?<!^)\s+-\s+", "\n- ", cleaned)
    cleaned = re.sub(r"(?<!^)\s+(\d+)\.\s+", r"\n\1. ", cleaned)
    cleaned = re.sub(r":\s*\n-", ":\n\n-", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    formatted_lines = []
    inside_group = False
    previous_was_question_heading = False
    lines = [line.strip() for line in cleaned.splitlines()]
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line:
            formatted_lines.append("")
            inside_group = False
            previous_was_question_heading = False
            index += 1
            continue

        is_bullet = line.startswith("- ")
        bullet_text = line[2:].strip() if is_bullet else line
        is_group_heading = is_bullet and bullet_text.rstrip("* ").endswith(":")
        is_question_heading = bullet_text.rstrip("* ").endswith("?") and not bullet_text.startswith("**")

        if is_group_heading:
            formatted_lines.append(bullet_text)
        elif is_question_heading:
            heading = bullet_text.strip("* ")
            if formatted_lines and formatted_lines[-1] != "":
                formatted_lines.append("")
            formatted_lines.append(f"**{heading}**")
            previous_was_question_heading = True
            inside_group = False
            index += 1
            continue
        elif is_bullet and previous_was_question_heading:
            formatted_lines.append(bullet_text)
        elif is_bullet and inside_group:
            formatted_lines.append(f"  - {bullet_text}")
        else:
            formatted_lines.append(line)

        inside_group = is_group_heading or (inside_group and is_bullet and not is_question_heading)
        previous_was_question_heading = False
        index += 1

    return "\n".join(formatted_lines).strip()

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
