from sqlalchemy.orm import  mapped_column, Mapped, relationship
from sqlalchemy import String, Text,Integer, ForeignKey, DateTime
from datetime import datetime, timezone
from pgvector.sqlalchemy import Vector

from .base import Base

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key= True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"),
        nullable= False
    )

    chunk_index: Mapped[int] = mapped_column(Integer)

    content: Mapped[str] = mapped_column(Text)

    embedding: Mapped[list[float]] = mapped_column(Vector(384))

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default = datetime.now(timezone.utc),
        nullable = False
    )
    document = relationship("Document", back_populates="chunks")