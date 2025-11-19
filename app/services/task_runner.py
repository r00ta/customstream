from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Set

logger = logging.getLogger(__name__)

_active_tasks: Set[asyncio.Task] = set()


def schedule_background_task(coro: Awaitable[None]) -> asyncio.Task:
    """Schedule a coroutine to run in the background and track its lifecycle."""

    task = asyncio.create_task(coro)
    _active_tasks.add(task)

    def _cleanup(finished: asyncio.Task) -> None:
        _active_tasks.discard(finished)
        try:
            finished.result()
        except asyncio.CancelledError:
            logger.info("Background task cancelled")
        except Exception:  # noqa: BLE001
            logger.exception("Background task failed")

    task.add_done_callback(_cleanup)
    return task
