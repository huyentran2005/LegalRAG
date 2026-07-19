from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from .base import Base

class User(Base):
    __tablename__="users"
    id: Mapped[int] = mapped_column(primary_key = True)
    
    email: Mapped[str] = mapped_column(
        String(100),
        unique= True,
        nullable = False,
        index = True
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable= False
    )

    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable = True
    ) 

    avatar_url: Mapped[str] = mapped_column(
        String(255),
        nullable = True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default = True,
        nullable= False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default = datetime.now(timezone.utc),
        nullable = False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        nullable=False
    )