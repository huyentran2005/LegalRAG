from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, ForeignKey, String, Text, Enum,JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum as PyEnum
from .base import Base

class MessageRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key= True)

    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id"),
        nullable= False
    )

    role : Mapped[MessageRole] = mapped_column(
        Enum(MessageRole),
        nullable= False
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    citations: Mapped[list | None] = mapped_column(JSON, nullable= True)

    created_at: Mapped[datetime]= mapped_column(
        DateTime,
        default= lambda: datetime.now(timezone.utc)
    )

    session = relationship("ChatSession", back_populates= "messages")