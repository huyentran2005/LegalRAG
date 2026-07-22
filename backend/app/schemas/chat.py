from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Literal

class AskRequest(BaseModel):
    question: str
    sourceIds: List[int] | None = None
    sessionId: int | None = None

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

class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    text: str | None = None
    parts: List[MessagePart] | None = None
    usedSources: List[int] | None = None
    citations: dict[int, CitationOut] | None = None
    created_at: str

class ChatSessionOut(BaseModel):
    id: int
    title: str | None = None
    created_at: str
    messages: List[ChatMessageOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
