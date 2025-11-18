from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Artifact(Base, TimestampMixin):
    """Represents a file associated with an image."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ftype: Mapped[str] = mapped_column(String(64), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    image: Mapped["Image"] = relationship(back_populates="artifacts")


from app.models.image import Image  # noqa: E402
