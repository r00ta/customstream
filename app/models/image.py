from typing import List, Optional

from sqlalchemy import ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Image(Base, TimestampMixin):
    """Represents an image tracked by the simplestream manager."""

    __tablename__ = "images"
    __table_args__ = (UniqueConstraint("stream_id", "product_id", name="uq_stream_product"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    image_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    origin_product_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    origin_index_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    os: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    release: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    arch: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    subarch: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    kflavor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    krel: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    build_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    stream: Mapped["Stream"] = relationship(back_populates="images")
    artifacts: Mapped[List["Artifact"]] = relationship(back_populates="image", cascade="all, delete-orphan")
    mirror_job: Mapped[Optional["MirrorJob"]] = relationship(back_populates="image", uselist=False)


from app.models.stream import Stream  # noqa: E402
from app.models.artifact import Artifact  # noqa: E402
from app.models.mirror_job import MirrorJob  # noqa: E402
