from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.models import Image, MirrorJob
from app.schemas.image import ArtifactOut, ImageList, ImageOut
from app.schemas.job import MirrorJobList, MirrorJobOut
from app.schemas.upstream import MirrorJobSummary, MirrorRequest, MirrorResult, UpstreamProduct, UpstreamStream
from app.services import custom as custom_service
from app.services import mirror as mirror_service
from app.services import upstream as upstream_service
from app.services import mirror_job as mirror_job_service
from app.utils.enums import ImageStatus

router = APIRouter(prefix="/api")


async def get_session() -> AsyncSession:
    async for session in get_db_session():
        yield session


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/upstream/streams", response_model=list[UpstreamStream])
async def list_upstream_streams(index_url: str) -> list[UpstreamStream]:
    return await upstream_service.list_streams(index_url)


@router.get("/upstream/streams/{stream_id}/products", response_model=list[UpstreamProduct])
async def list_upstream_products(stream_id: str, index_url: str) -> list[UpstreamProduct]:
    return await upstream_service.list_products_for_stream(index_url, stream_id)


@router.post("/mirror", response_model=MirrorResult)
async def mirror_products(payload: MirrorRequest, session: AsyncSession = Depends(get_session)) -> MirrorResult:
    enqueued_products: list[str] = []
    skipped: list[str] = []
    job_summaries: list[MirrorJobSummary] = []

    for product_id in payload.product_ids:
        active_image = await session.scalar(
            select(Image).where(
                Image.product_id == product_id,
                Image.status == ImageStatus.MIRRORING.value,
            )
        )
        if active_image:
            skipped.append(f"{product_id} (already mirroring)")
            continue

        job = await mirror_job_service.find_active_job(session, product_id)
        if job:
            skipped.append(f"{product_id} (already queued)")
            continue

        job = await mirror_job_service.enqueue_job(session, str(payload.index_url), product_id)
        enqueued_products.append(product_id)
        job_summaries.append(MirrorJobSummary(job_id=job.id, product_id=job.product_id))

    if not enqueued_products and not skipped:
        raise HTTPException(status_code=400, detail="No products selected for mirroring")

    if enqueued_products:
        try:
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            raise HTTPException(status_code=500, detail="Failed to enqueue mirror jobs") from exc
        mirror_job_service.trigger_job_runner()

    return MirrorResult(enqueued=enqueued_products, skipped=skipped, jobs=job_summaries)


@router.get("/mirror/jobs", response_model=MirrorJobList)
async def list_mirror_jobs(session: AsyncSession = Depends(get_session)) -> MirrorJobList:
    result = await session.execute(select(MirrorJob).order_by(MirrorJob.created_at.desc()).limit(10))
    jobs = result.scalars().all()
    return MirrorJobList(items=[_serialize_job(job) for job in jobs])


@router.get("/images", response_model=ImageList)
async def list_images(session: AsyncSession = Depends(get_session)) -> ImageList:
    result = await session.execute(
        select(Image)
        .options(selectinload(Image.artifacts), selectinload(Image.stream))
        .order_by(Image.created_at.desc())
    )
    images = result.scalars().unique().all()
    items = [_serialize_image(image) for image in images]
    return ImageList(items=items)


@router.delete("/images/{image_id}", status_code=204)
async def delete_image(image_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await custom_service.delete_image(session, image_id)


@router.post("/custom/images", response_model=ImageOut)
async def create_custom_image(
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    os_name: str = Form("custom"),
    release: str = Form(...),
    version: str = Form(...),
    arch: str = Form(...),
    label: str | None = Form(None),
    subarch: str | None = Form(None),
    description: str | None = Form(None),
    kflavor: str | None = Form(None),
    krel: str | None = Form(None),
    release_codename: str | None = Form(None),
    subarches: str | None = Form(None),
    kernel: UploadFile | None = File(None),
    initrd: UploadFile | None = File(None),
    rootfs: UploadFile | None = File(None),
    manifest: UploadFile | None = File(None),
) -> ImageOut:
    uploads = {
        key: file
        for key, file in {"kernel": kernel, "initrd": initrd, "rootfs": rootfs, "manifest": manifest}.items()
        if file
    }

    try:
        image_id = await custom_service.create_custom_image(
            session,
            name=name,
            os_name=os_name,
            release=release,
            version=version,
            arch=arch,
            label=label,
            subarch=subarch,
            description=description,
            kflavor=kflavor,
            krel=krel,
            release_codename=release_codename,
            subarches=subarches,
            uploads=uploads,
        )
    except custom_service.CustomImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await session.execute(
        select(Image).options(selectinload(Image.artifacts), selectinload(Image.stream)).where(Image.id == image_id)
    )
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=500, detail="Failed to load created image")
    return _serialize_image(image)


@router.get("/simplestream", response_model=dict[str, str])
async def simplestream_info() -> dict[str, str]:
    return {"index": "/simplestreams/streams/v1/index.json"}


def _serialize_image(image: Image) -> ImageOut:
    artifacts = [
        ArtifactOut(
            name=a.name,
            ftype=a.ftype,
            relative_path=a.relative_path,
            size=a.size,
            sha256=a.sha256,
            download_url=f"/simplestreams/{a.relative_path}",
        )
        for a in sorted(image.artifacts, key=lambda item: item.name)
    ]
    stream = image.stream
    meta = image.meta or {}
    release_codename = meta.get("release_codename")
    subarches = meta.get("subarches")
    if subarches is not None:
        subarches = str(subarches)
    status_detail = None
    if image.status != ImageStatus.READY.value:
        status_detail = meta.get("error") or meta.get("status_detail")
    return ImageOut(
        id=image.id,
        product_id=image.product_id,
        name=image.name,
        stream_id=stream.stream_id if stream else "",
        stream_path=stream.path if stream else "",
        image_type=image.image_type,
        status=image.status,
        status_detail=status_detail,
        origin_product_url=image.origin_product_url,
        origin_index_url=image.origin_index_url,
        os=image.os,
        release=image.release,
        version=image.version,
        arch=image.arch,
        subarch=image.subarch,
        release_codename=release_codename,
        subarches=subarches,
        label=image.label,
        kflavor=image.kflavor,
        krel=image.krel,
        build_id=image.build_id,
        artifacts=artifacts,
        created_at=image.created_at,
        updated_at=image.updated_at,
    )


def _serialize_job(job: MirrorJob) -> MirrorJobOut:
    return MirrorJobOut(
        id=job.id,
        product_id=job.product_id,
        index_url=job.index_url,
        status=job.status,
        message=job.message,
        progress=job.progress,
        image_id=job.image_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )