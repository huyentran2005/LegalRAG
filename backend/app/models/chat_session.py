from datetime import datetime, timezone
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime, ForeignKey, String, Integer

from .base import Base 

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key= True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable = False
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable= True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default= lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session")
