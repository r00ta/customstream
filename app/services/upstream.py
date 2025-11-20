from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.config import get_settings
from app.schemas.upstream import UpstreamProduct, UpstreamStream

settings = get_settings()


async def fetch_index(index_url: str) -> dict[str, Any]:
    """Fetch an upstream simplestream index JSON."""

    async with httpx.AsyncClient(timeout=settings.upstream_request_timeout, headers={"User-Agent": settings.user_agent}) as client:
        response = await client.get(index_url)
        response.raise_for_status()
        return response.json()


def _ensure_stream_structure(index: dict[str, Any]) -> dict[str, Any]:
    if "index" not in index:
        raise ValueError("Invalid simplestream index: missing 'index' key")
    return index["index"]


async def list_streams(index_url: str) -> list[UpstreamStream]:
    """List streams contained in the specified index URL."""

    payload = await fetch_index(index_url)
    streams = _ensure_stream_structure(payload)
    results: list[UpstreamStream] = []
    for stream_id, entry in streams.items():
        results.append(
            UpstreamStream(
                stream_id=stream_id,
                path=entry.get("path"),
                datatype=entry.get("datatype", "image-ids"),
                format=entry.get("format", "products:1.0"),
                products=list(entry.get("products", [])),
                updated=entry.get("updated"),
                origin_index_url=index_url,
            )
        )
    return results


async def list_products_for_stream(index_url: str, stream_id: str) -> list[UpstreamProduct]:
    """Return metadata for products inside a specific stream."""

    payload = await fetch_index(index_url)
    stream_entry = _ensure_stream_structure(payload).get(stream_id)
    if not stream_entry:
        raise ValueError(f"Stream '{stream_id}' not found in index")

    product_path = stream_entry.get("path")
    if not product_path:
        raise ValueError(f"Stream '{stream_id}' is missing a product path")

    product_url = urljoin(_resolve_root_base(index_url), product_path)

    async with httpx.AsyncClient(timeout=settings.upstream_request_timeout, headers={"User-Agent": settings.user_agent}) as client:
        response = await client.get(product_url)
        response.raise_for_status()
        product_payload = response.json()

    products = product_payload.get("products", {})

    sortable_products: list[tuple[str | None, str, dict[str, Any]]] = []
    for pid, meta in products.items():
        latest = _latest_version(meta.get("versions", {}))
        latest_key = latest[0] if latest else None
        sortable_products.append((latest_key, pid, meta))

    sortable_products.sort(key=lambda item: ((item[0] or ""), item[1]), reverse=True)

    return [
        _serialize_product(stream_id, product_path, index_url, product_id, meta, latest_key)
        for latest_key, product_id, meta in sortable_products
    ]


def _serialize_product(
    stream_id: str,
    stream_path: str,
    index_url: str,
    product_id: str,
    meta: dict[str, Any],
    latest_version_key: str | None,
) -> UpstreamProduct:
    """Build an UpstreamProduct from the upstream metadata."""

    return UpstreamProduct(
        product_id=product_id,
        name=_product_name(meta),
        stream_id=stream_id,
        stream_path=stream_path,
        stream_updated=meta.get("updated"),
        origin_index_url=index_url,
        os=meta.get("os"),
        release=meta.get("release"),
        version=meta.get("version"),
        arch=meta.get("arch"),
        subarch=meta.get("subarch"),
        label=meta.get("label"),
        kflavor=meta.get("kflavor"),
        krel=meta.get("krel"),
        build_id=latest_version_key,
    )


def _product_name(meta: dict[str, Any]) -> str:
    release_title = meta.get("release_title") or meta.get("release") or "Unknown release"
    arch = meta.get("arch") or "unknown"
    subarch = meta.get("subarch")
    if subarch:
        return f"{release_title} {arch} ({subarch})"
    return f"{release_title} {arch}"


def _latest_version(versions: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if not versions:
        return None
    latest_key = max(versions.keys())
    return latest_key, versions[latest_key]


def _resolve_root_base(index_url: str) -> str:
    parts = urlsplit(index_url)
    prefix, _, _ = parts.path.partition("/streams/")
    if not prefix.endswith("/"):
        prefix += "/"
    return urlunsplit((parts.scheme, parts.netloc, prefix, "", ""))
