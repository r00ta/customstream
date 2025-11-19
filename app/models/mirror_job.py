from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin
from app.utils.enums import JobStatus


class MirrorJob(Base, TimestampMixin):
    """Background mirror job tracking entry."""

    __tablename__ = "mirror_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    index_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.QUEUED.value)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    image_id: Mapped[Optional[int]] = mapped_column(ForeignKey("images.id"), nullable=True)
    image: Mapped["Image"] = relationship(back_populates="mirror_job")

    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


from app.models.image import Image  # noqa: E402  (circular import resolution)
