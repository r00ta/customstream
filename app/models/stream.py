from typing import List, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Stream(Base, TimestampMixin):
    """Represents a simplestream stream definition."""

    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    stream_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    datatype: Mapped[str] = mapped_column(String(64), default="image-ids", nullable=False)
    format: Mapped[str] = mapped_column(String(32), default="products:1.0", nullable=False)
    source_index_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    images: Mapped[List["Image"]] = relationship(back_populates="stream", cascade="all, delete-orphan")


from app.models.image import Image  # noqa: E402  (circular import resolution)
