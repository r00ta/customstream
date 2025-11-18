from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple

import httpx
from fastapi import UploadFile

from app.core.config import get_settings

settings = get_settings()


async def download_with_hash(client: httpx.AsyncClient, url: str, destination: Path) -> Tuple[int, str]:
    """Download a file and return its size and sha256 checksum."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    size = 0

    async with client.stream("GET", url) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            async for chunk in response.aiter_bytes():
                handle.write(chunk)
                size += len(chunk)
                hasher.update(chunk)

    return size, hasher.hexdigest()


def safe_remove(path: Path) -> None:
    """Remove a file if it exists."""

    if path.exists():
        path.unlink()


def safe_remove_tree(path: Path) -> None:
    """Remove a directory tree if it exists."""

    if path.is_dir():
        for child in path.iterdir():
            if child.is_dir():
                safe_remove_tree(child)
            else:
                child.unlink()
        path.rmdir()
    elif path.exists():
        path.unlink()


async def save_upload(upload: UploadFile, destination: Path) -> Tuple[int, str]:
    """Persist an uploaded file to disk and return its size and checksum."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    size = 0

    with destination.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            size += len(chunk)
            hasher.update(chunk)

    await upload.seek(0)
    return size, hasher.hexdigest()
