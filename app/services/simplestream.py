from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import Image, Stream

settings = get_settings()


RFC_1123_FORMAT = "%a, %d %b %Y %H:%M:%S +0000"


def _now_rfc1123() -> str:
    return datetime.now(timezone.utc).strftime(RFC_1123_FORMAT)


def _storage_path(*segments: str) -> Path:
    return settings.storage_path.joinpath(*segments)


async def rebuild_simplestream_files(session: AsyncSession) -> None:
    """Regenerate index and product files from the current database state."""

    result = await session.execute(
        select(Stream)
        .options(selectinload(Stream.images).selectinload(Image.artifacts))
        .order_by(Stream.stream_id)
    )
    streams: list[Stream] = list(result.scalars().unique())

    index_payload: dict[str, Any] = {
        "format": "index:1.0",
        "index": {},
        "updated": _now_rfc1123(),
    }

    for stream in streams:
        if not stream.images:
            continue
        content_id = stream.stream_id
        index_payload["index"][stream.stream_id] = {
            "datatype": stream.datatype,
            "format": stream.format,
            "path": stream.path,
            "products": sorted(image.product_id for image in stream.images),
            "updated": _now_rfc1123(),
            "content_id": content_id,
        }
        await _write_stream_products(stream, content_id)

    index_file = _storage_path("streams", "v1", "index.json")
    index_file.parent.mkdir(parents=True, exist_ok=True)
    index_file.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")


async def _write_stream_products(stream: Stream, content_id: str) -> None:
    """Write the product file representing all images inside a stream."""

    products_payload: dict[str, Any] = {
        "datatype": "image-ids",
        "format": "products:1.0",
        "products": {},
        "updated": _now_rfc1123(),
        "content_id": content_id,
    }

    for image in sorted(stream.images, key=lambda item: item.product_id):
        entry = deepcopy(image.meta or {})
        if not entry:
            continue
        entry.setdefault("os", image.os)
        entry.setdefault("release", image.release)
        entry.setdefault("version", image.version)
        entry.setdefault("arch", image.arch)
        entry.setdefault("subarch", image.subarch)
        if image.meta:
            release_codename = image.meta.get("release_codename")
            if release_codename:
                entry.setdefault("release_codename", release_codename)
            subarches = image.meta.get("subarches")
            if subarches:
                entry.setdefault("subarches", subarches)
        entry.setdefault("label", image.label)
        entry.setdefault("kflavor", image.kflavor)
        entry.setdefault("krel", image.krel)

        versions = entry.get("versions") or {}
        if versions:
            for version_key, version_data in versions.items():
                items = version_data.get("items") or {}
                for artifact in image.artifacts:
                    if artifact.name in items:
                        items[artifact.name]["path"] = artifact.relative_path
                        if artifact.sha256:
                            items[artifact.name]["sha256"] = artifact.sha256
                        if artifact.size:
                            items[artifact.name]["size"] = artifact.size
                version_data["items"] = items
            entry["versions"] = versions

        clean_entry = {key: value for key, value in entry.items() if value is not None}
        products_payload["products"][image.product_id] = clean_entry

    product_file = _storage_path(*Path(stream.path).parts)
    product_file.parent.mkdir(parents=True, exist_ok=True)
    product_file.write_text(json.dumps(products_payload, indent=2), encoding="utf-8")
