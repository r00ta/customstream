from datetime import datetime

from pydantic import BaseModel


class ArtifactOut(BaseModel):
    """Represents artifact metadata returned to clients."""

    name: str
    ftype: str
    relative_path: str
    size: int | None = None
    sha256: str | None = None
    download_url: str | None = None


class ImageOut(BaseModel):
    """Represents an image in responses."""

    id: int
    product_id: str
    name: str
    stream_id: str
    stream_path: str
    image_type: str
    status: str
    status_detail: str | None = None
    origin_product_url: str | None = None
    origin_index_url: str | None = None

    os: str | None = None
    release: str | None = None
    version: str | None = None
    arch: str | None = None
    subarch: str | None = None
    release_codename: str | None = None
    subarches: str | None = None
    label: str | None = None
    kflavor: str | None = None
    krel: str | None = None
    build_id: str | None = None

    artifacts: list[ArtifactOut]
    created_at: datetime
    updated_at: datetime


class ImageList(BaseModel):
    """Collection wrapper for image listings."""

    items: list[ImageOut]
