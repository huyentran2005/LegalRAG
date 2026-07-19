from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime,ForeignKey, Enum
from datetime import datetime, timezone
from enum import Enum as PyEnum
from .base import Base

class DocumentStatus(str, PyEnum):
    PROCESSING = "PROCESSING"
    COMPLETED= "COMPLETED"
    FAILED = "FAILED"

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key= True)

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable= False
    )

    filename: Mapped[str] = mapped_column(String(255))

    storage_path: Mapped[str] = mapped_column(String(500))

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default= DocumentStatus.PROCESSING
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default = datetime.now(timezone.utc),
        nullable = False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    owner = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates= "document")

