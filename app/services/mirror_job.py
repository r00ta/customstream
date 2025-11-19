from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import async_session_factory
from app.services import mirror as mirror_service

logger = logging.getLogger(__name__)


async def run_mirror_job(index_url: str, product_id: str) -> None:
    """Download and register a single product in a dedicated session."""

    async with async_session_factory() as session:
        try:
            await mirror_service.mirror_product(session, index_url, product_id)
        except mirror_service.MirrorError as exc:
            logger.warning("Mirroring failed for %s: %s", product_id, exc)
        except SQLAlchemyError as exc:  # pragma: no cover - defensive logging
            logger.exception("Database failure while mirroring %s", product_id)
            raise
        except Exception as exc:  # noqa: BLE001 - ensure unexpected errors are surfaced
            logger.exception("Unexpected error while mirroring %s", product_id)
            raise
