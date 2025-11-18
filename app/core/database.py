from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


engine: AsyncEngine = create_async_engine(str(settings.database_url), future=True, echo=False)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependency that yields a database session per request."""

    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create database schema if it does not already exist."""

    from app import models  # noqa: WPS433  (imported for side effects)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
