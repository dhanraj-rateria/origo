from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..settings import Settings

def build_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://", 1),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        echo=settings.db_echo,
    )

def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)

async def get_session(request) -> AsyncIterator[AsyncSession]:  # FastAPI dependency
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session, session.begin():
        yield session