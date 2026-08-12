from sqlalchemy.orm import Session
import re
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession

MAX_HISTORY_TURNS = 10


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


def _format_memory_for_prompt(memory: list[dict]) -> str:
    lines = []
    for turn in memory:
        speaker = "Người dùng" if turn.get("role") == "user" else "Trợ lý"
        content = re.sub(r"\s+", " ", turn.get("content", "")).strip()
        if content:
            lines.append(f"{speaker}: {content}")
    return "\n".join(lines)
