# origo-edge/tests/conftest.py
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from origo_edge.db.base import Base
from origo_edge.db.models import device, job, key  # noqa: F401
from origo_edge.main import create_app
from origo_edge.settings import Settings


@pytest_asyncio.fixture(scope="session")
async def pg_url() -> AsyncIterator[str]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "asyncpg")


@pytest_asyncio.fixture
async def app(pg_url: str):
    settings = Settings(
        database_url=pg_url, env="local", auth_disabled=True, edge_device_token="test-token",
    )
    application = create_app(settings)

    engine = create_async_engine(pg_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)   # clean slate per test
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c