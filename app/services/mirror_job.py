from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import async_session_factory
from app.models import MirrorJob
from app.services import mirror as mirror_service
from app.services.task_runner import schedule_background_task
from app.utils.enums import JobStatus

logger = logging.getLogger(__name__)

_worker_lock = asyncio.Lock()
_worker_task: Optional[asyncio.Task] = None


async def find_active_job(session, product_id: str) -> Optional[MirrorJob]:
    return await session.scalar(
        select(MirrorJob).where(
            MirrorJob.product_id == product_id,
            MirrorJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        )
    )


async def enqueue_job(session, index_url: str, product_id: str) -> MirrorJob:
    job = MirrorJob(
        index_url=index_url,
        product_id=product_id,
        status=JobStatus.QUEUED.value,
        progress=0,
    )
    session.add(job)
    await session.flush()
    return job


def trigger_job_runner() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = schedule_background_task(_process_queue())


async def resume_pending_jobs() -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(MirrorJob).where(MirrorJob.status == JobStatus.RUNNING.value)
        )
        restarted = 0
        for job in result.scalars():
            job.status = JobStatus.QUEUED.value
            job.message = "Resumed after service restart"
            job.started_at = None
            job.finished_at = None
            job.progress = 0
            restarted += 1
        if restarted:
            await session.commit()
    trigger_job_runner()


async def _process_queue() -> None:
    async with _worker_lock:
        while True:
            async with async_session_factory() as session:
                job = await session.scalar(
                    select(MirrorJob)
                    .where(MirrorJob.status == JobStatus.QUEUED.value)
                    .order_by(MirrorJob.created_at.asc())
                )
                if not job:
                    break

                job.status = JobStatus.RUNNING.value
                job.started_at = datetime.utcnow()
                job.message = None
                job.progress = 10
                await session.commit()

                job_id = job.id
                index_url = job.index_url
                product_id = job.product_id

            try:
                async with async_session_factory() as worker_session:
                    image_id = await mirror_service.mirror_product(worker_session, index_url, product_id)
            except mirror_service.MirrorError as exc:
                await _mark_job_failed(job_id, str(exc))
            except SQLAlchemyError as exc:  # pragma: no cover - defensive logging
                logger.exception("Database error while mirroring %s", product_id)
                await _mark_job_failed(job_id, f"Database failure: {exc}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error while mirroring %s", product_id)
                await _mark_job_failed(job_id, f"Unexpected error: {exc}")
            else:
                await _mark_job_completed(job_id, image_id)


async def _mark_job_completed(job_id: int, image_id: int) -> None:
    async with async_session_factory() as session:
        job = await session.get(MirrorJob, job_id)
        if not job:
            return
        job.status = JobStatus.COMPLETED.value
        job.progress = 100
        job.finished_at = datetime.utcnow()
        job.image_id = image_id
        await session.commit()


async def _mark_job_failed(job_id: int, message: str) -> None:
    async with async_session_factory() as session:
        job = await session.get(MirrorJob, job_id)
        if not job:
            return
        job.status = JobStatus.FAILED.value
        job.progress = 100
        job.finished_at = datetime.utcnow()
        job.message = message[:2000]
        await session.commit()

