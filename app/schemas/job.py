from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MirrorJobOut(BaseModel):
    """Serialized representation of a mirror job."""

    id: int
    product_id: str
    index_url: str
    status: str
    message: Optional[str] = None
    progress: int
    image_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class MirrorJobList(BaseModel):
    """List wrapper for mirror jobs."""

    items: list[MirrorJobOut]
