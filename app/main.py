from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.database import init_db
from app.services import mirror_job as mirror_job_service

settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
async def startup_event() -> None:
    await init_db()
    await mirror_job_service.resume_pending_jobs()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.allow_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

app.mount(
    "/simplestreams",
    StaticFiles(directory=str(settings.storage_path), html=False),
    name="simplestreams",
)
app.mount("/", StaticFiles(directory=str(settings.frontend_path), html=True), name="frontend")
