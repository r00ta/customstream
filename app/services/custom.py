from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, Tuple

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Artifact, Image, Stream
from app.services.simplestream import rebuild_simplestream_files
from app.services.storage import save_upload, safe_remove
from app.utils.enums import ImageStatus, ImageType
from app.utils.text import slugify

settings = get_settings()

CUSTOM_STREAM_ID = "com.local.maas:custom:download"
CUSTOM_STREAM_PATH = "streams/v1/com.local.maas:custom:download.json"

FILE_TYPE_MAP: Dict[str, Tuple[str, str]] = {
    "kernel": ("boot-kernel", "boot-kernel"),
    "initrd": ("boot-initrd", "boot-initrd"),
    "rootfs": ("squashfs", "squashfs"),
    "manifest": ("manifest", "squashfs.manifest"),
}


class CustomImageError(Exception):
    """Signals a failure when handling custom images."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


async def ensure_custom_stream(session: AsyncSession) -> Stream:
    stream = await session.scalar(select(Stream).where(Stream.stream_id == CUSTOM_STREAM_ID))
    if stream:
        return stream

    stream = Stream(
        stream_id=CUSTOM_STREAM_ID,
        path=CUSTOM_STREAM_PATH,
        datatype="image-ids",
        format="products:1.0",
        source_index_url="local",
    )
    session.add(stream)
    await session.flush()
    return stream


async def create_custom_image(
    session: AsyncSession,
    name: str,
    os_name: str,
    release: str,
    version: str,
    arch: str,
    *,
    label: str | None = None,
    subarch: str | None = None,
    description: str | None = None,
    kflavor: str | None = None,
    krel: str | None = None,
    release_codename: str | None = None,
    subarches: str | None = None,
    uploads: Dict[str, UploadFile],
) -> int:
    """Create a custom image from uploaded artifacts."""

    stream = await ensure_custom_stream(session)

    if not uploads:
        raise CustomImageError("At least one artifact must be provided")

    if "rootfs" in uploads and "manifest" not in uploads:
        raise CustomImageError("Upload the matching manifest alongside the root filesystem")

    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    name = name.strip()
    os_name = os_name.strip()
    release = release.strip()
    version = version.strip()
    arch = arch.strip()
    if not name or not release or not version or not arch:
        raise CustomImageError("Name, release, version, and arch are required")
    label = _clean(label)
    subarch = _clean(subarch)
    description = _clean(description)
    kflavor = _clean(kflavor)
    krel = _clean(krel)
    release_codename = _clean(release_codename)
    subarches = subarches.strip() if subarches else None

    slug = slugify(name)
    if not slug:
        slug = slugify(f"{release}-{version}") or arch

    def _segment(value: str | None) -> str | None:
        if not value:
            return None
        return value.replace(" ", "-")

    release_segment = _segment(release) or "custom"
    version_segment = _segment(version)
    arch_segment = _segment(arch) or "unknown"
    subarch_segment = _segment(subarch)

    segments = ["com.local.maas.custom", "v3", slug]
    if release_segment:
        segments.append(release_segment)
    if version_segment and version_segment not in segments:
        segments.append(version_segment)
    segments.append(arch_segment)
    if subarch_segment:
        segments.append(subarch_segment)

    product_id = ":".join(segments)
    build_id = _timestamp()

    # Remove any existing image with same product id
    await _delete_by_product_id(session, stream, product_id)

    version_entry: Dict[str, dict] = {"items": {}}
    if description:
        version_entry["description"] = description
    artifact_rows: list[Artifact] = []

    for key, upload in uploads.items():
        if not upload:
            continue
        if key not in FILE_TYPE_MAP:
            raise CustomImageError(f"Unsupported artifact type '{key}'")
        item_key, default_name = FILE_TYPE_MAP[key]
        filename = default_name
        relative_path = f"custom/{product_id}/{filename}"
        destination = settings.storage_path / relative_path

        size, sha256 = await save_upload(upload, destination)

        item_meta = {
            "ftype": item_key,
            "path": relative_path,
            "size": size,
            "sha256": sha256,
        }
        version_entry["items"][item_key] = item_meta

        artifact_rows.append(
            Artifact(
                name=item_key,
                ftype=item_key,
                relative_path=relative_path,
                size=size,
                sha256=sha256,
                source_url=None,
            )
        )

    if not version_entry["items"]:
        raise CustomImageError("No valid artifacts uploaded")

    parsed_subarches = []
    normalized_subarches: str | None = None
    if subarches:
        seen: set[str] = set()
        for token in re.split(r"[,\s]+", subarches):
            trimmed = token.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            parsed_subarches.append(trimmed)
        if parsed_subarches:
            normalized_subarches = ",".join(parsed_subarches)

    meta = {
        "os": os_name,
        "release": release,
        "release_title": release,
        "version": version,
        "label": label or "custom",
        "arch": arch,
        "subarch": subarch,
        "kflavor": kflavor,
        "krel": krel,
        "versions": {build_id: version_entry},
    }
    if release_codename:
        meta["release_codename"] = release_codename
    if normalized_subarches:
        meta["subarches"] = normalized_subarches

    image = Image(
        stream_id=stream.id,
        product_id=product_id,
        name=name,
        image_type=ImageType.CUSTOM.value,
        status=ImageStatus.READY.value,
        origin_product_url=None,
        origin_index_url="local",
        os=os_name,
        release=release,
        version=version,
        arch=arch,
        subarch=subarch,
        label=label or "custom",
        kflavor=kflavor,
        krel=krel,
        build_id=build_id,
        meta=meta,
    )
    session.add(image)
    await session.flush()

    for artifact in artifact_rows:
        artifact.image_id = image.id
        session.add(artifact)

    await session.commit()
    await rebuild_simplestream_files(session)
    await session.commit()

    return image.id


async def delete_image(session: AsyncSession, image_id: int) -> None:
    image = await session.scalar(select(Image).where(Image.id == image_id))
    if not image:
        return

    await session.refresh(image, attribute_names=["artifacts"])
    for artifact in image.artifacts:
        safe_remove(settings.storage_path / artifact.relative_path)

    await session.delete(image)
    await session.commit()
    await rebuild_simplestream_files(session)
    await session.commit()


async def _delete_by_product_id(session: AsyncSession, stream: Stream, product_id: str) -> None:
    existing = await session.scalar(
        select(Image).where(Image.stream_id == stream.id, Image.product_id == product_id)
    )
    if not existing:
        return

    await session.refresh(existing, attribute_names=["artifacts"])
    for artifact in existing.artifacts:
        safe_remove(settings.storage_path / artifact.relative_path)
    await session.delete(existing)
    await session.flush()