from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Literal

from app.models.chat_message import ChatMessage, MessageRole
from app.models.chat_session import ChatSession

class AskRequest(BaseModel):
    question: str
    sourceIds: List[int] | None = None
    sessionId: int | None = None
    provider: str 

class SourceOut(BaseModel):
    id: int
    filename: str
    file_type: str
    page_count: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes= True)

class CitationOut(BaseModel):
    sourceId: int
    sourceName: str
    page: str
    excerpt: str

class MessagePart(BaseModel):
    text: str | None = None
    cite: int | None = None

class AnswerResponse(BaseModel):
    sessionId: int
    answer: str
    sources: List[SourceOut] = Field(default_factory=list)
    citations: dict[int, CitationOut] = Field(default_factory=dict)
    parts: List[MessagePart] = Field(default_factory=list)
    usedSources: List[int] = Field(default_factory=list)
    token: int

class ChatMessageOut(BaseModel):
    id: int
    sessionId: int
    role: Literal["user", "assistant"]
    text: str | None = None
    parts: List[MessagePart] | None = None
    usedSources: List[int] | None = None
    citations: dict[int, CitationOut] | None = None
    createdAt: datetime
    token: int

class ChatSessionOut(BaseModel):
    id: int
    title: str | None = None
    created_at: str
    messages: List[ChatMessageOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

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
