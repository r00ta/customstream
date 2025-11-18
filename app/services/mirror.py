from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Artifact, Image, Stream
from app.schemas.upstream import MirrorRequest
from app.services.simplestream import rebuild_simplestream_files
from app.services.storage import download_with_hash, safe_remove
from app.utils.enums import ImageStatus, ImageType

settings = get_settings()


class MirrorError(Exception):
    """Raised when mirroring a product fails."""


async def mirror_products(session: AsyncSession, payload: MirrorRequest) -> Tuple[List[int], List[str]]:
    """Mirror the selected products from the upstream simplestream."""

    index_data = await _fetch_json(payload.index_url)
    available_streams = index_data.get("index", {})
    if not available_streams:
        raise MirrorError("Upstream index does not contain any streams")

    stream_cache: Dict[str, Dict[str, Any]] = {}
    mirrored_ids: List[int] = []
    failures: List[str] = []

    root_base = _resolve_root_base(str(payload.index_url))

    async with httpx.AsyncClient(timeout=settings.upstream_request_timeout, headers={"User-Agent": settings.user_agent}) as client:
        for product_id in payload.product_ids:
            try:
                stream_id, stream_entry = _find_stream_for_product(product_id, available_streams)
                stream = await _get_or_create_stream(session, stream_id, stream_entry, str(payload.index_url))

                product_payload = await _get_product_payload(stream_id, stream_entry, root_base, stream_cache)
                product_meta = product_payload.get("products", {}).get(product_id)
                if not product_meta:
                    raise MirrorError("Product metadata missing in upstream response")

                version_key, version_data = _latest_version(product_meta.get("versions", {}))
                if not version_data:
                    raise MirrorError("No version entries available for product")

                await _remove_existing_image(session, stream, product_id)

                entry_copy = _build_entry_copy(product_meta, version_key, version_data)

                items = version_data.get("items", {})
                artifact_rows: List[Artifact] = []

                for item_name, item_meta in items.items():
                    relative_path = item_meta.get("path")
                    if not relative_path:
                        raise MirrorError(f"Item '{item_name}' missing path")

                    download_url = urljoin(root_base, relative_path)
                    destination = settings.storage_path / relative_path

                    try:
                        size, sha256 = await download_with_hash(client, download_url, destination)
                    except Exception as exc:  # noqa: BLE001
                        safe_remove(destination)
                        raise MirrorError(f"Failed to download '{relative_path}': {exc}") from exc

                    item_meta = deepcopy(item_meta)
                    item_meta["path"] = relative_path
                    item_meta["size"] = size
                    item_meta["sha256"] = sha256

                    entry_copy["versions"][version_key]["items"][item_name] = item_meta

                    artifact_rows.append(
                        Artifact(
                            name=item_name,
                            ftype=item_meta.get("ftype", item_name),
                            relative_path=relative_path,
                            size=size,
                            sha256=sha256,
                            source_url=download_url,
                        )
                    )

                image = Image(
                    stream_id=stream.id,
                    product_id=product_id,
                    name=_derive_image_name(product_meta),
                    image_type=ImageType.MIRRORED.value,
                    status=ImageStatus.READY.value,
                    origin_product_url=urljoin(root_base, stream_entry.get("path", "")),
                    origin_index_url=str(payload.index_url),
                    os=product_meta.get("os"),
                    release=product_meta.get("release"),
                    version=product_meta.get("version"),
                    arch=product_meta.get("arch"),
                    subarch=product_meta.get("subarch"),
                    label=product_meta.get("label"),
                    kflavor=product_meta.get("kflavor"),
                    krel=product_meta.get("krel"),
                    build_id=version_key,
                    meta=entry_copy,
                )
                session.add(image)
                await session.flush()

                for artifact in artifact_rows:
                    artifact.image_id = image.id
                    session.add(artifact)

                mirrored_ids.append(image.id)

            except Exception as exc:  # noqa: BLE001
                failures.append(f"{product_id}: {exc}")

    await session.commit()
    await rebuild_simplestream_files(session)
    await session.commit()

    return mirrored_ids, failures


async def _get_or_create_stream(session: AsyncSession, stream_id: str, entry: dict[str, Any], index_url: str) -> Stream:
    stream = await session.scalar(select(Stream).where(Stream.stream_id == stream_id))
    if stream:
        stream.path = entry.get("path", stream.path)
        stream.datatype = entry.get("datatype", stream.datatype)
        stream.format = entry.get("format", stream.format)
        stream.source_index_url = index_url
        await session.flush()
        return stream

    stream = Stream(
        stream_id=stream_id,
        path=entry.get("path"),
        datatype=entry.get("datatype", "image-ids"),
        format=entry.get("format", "products:1.0"),
        source_index_url=index_url,
    )
    session.add(stream)
    await session.flush()
    return stream


async def _get_product_payload(stream_id: str, entry: dict[str, Any], base_url: str, cache: Dict[str, dict[str, Any]]) -> dict[str, Any]:
    if stream_id in cache:
        return cache[stream_id]

    product_url = urljoin(base_url, entry.get("path", ""))
    payload = await _fetch_json(product_url)
    cache[stream_id] = payload
    return payload


async def _fetch_json(url: str | HttpUrl) -> dict[str, Any]:
    target = str(url)
    async with httpx.AsyncClient(timeout=settings.upstream_request_timeout, headers={"User-Agent": settings.user_agent}) as client:
        response = await client.get(target)
        response.raise_for_status()
        return response.json()


def _find_stream_for_product(product_id: str, streams: dict[str, Any]) -> Tuple[str, dict[str, Any]]:
    for stream_id, entry in streams.items():
        if product_id in entry.get("products", []):
            return stream_id, entry
    raise MirrorError(f"Product '{product_id}' not present in upstream index")


def _latest_version(versions: dict[str, Any]) -> Tuple[str, dict[str, Any]]:
    if not versions:
        raise MirrorError("No versions available")
    version_key = max(versions.keys())
    return version_key, deepcopy(versions[version_key])


async def _remove_existing_image(session: AsyncSession, stream: Stream, product_id: str) -> None:
    existing = await session.scalar(
        select(Image).where(Image.stream_id == stream.id, Image.product_id == product_id)
    )
    if not existing:
        return

    for artifact in existing.artifacts:
        safe_remove(settings.storage_path / artifact.relative_path)
    await session.delete(existing)
    await session.flush()


def _build_entry_copy(meta: dict[str, Any], version_key: str, version_data: dict[str, Any]) -> dict[str, Any]:
    entry = {key: deepcopy(value) for key, value in meta.items() if key != "versions"}
    entry["versions"] = {version_key: deepcopy(version_data)}
    entry["versions"][version_key]["items"] = deepcopy(version_data.get("items", {}))
    return entry


def _derive_image_name(meta: dict[str, Any]) -> str:
    title = meta.get("release_title") or meta.get("label") or "Image"
    arch = meta.get("arch")
    if arch:
        return f"{title} ({arch})"
    return title


def _resolve_root_base(index_url: str) -> str:
    parts = urlsplit(index_url)
    prefix, _, _ = parts.path.partition("/streams/")
    if not prefix.endswith("/"):
        prefix += "/"
    return urlunsplit((parts.scheme, parts.netloc, prefix, "", ""))