from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.errors import install_exception_handlers
from .api.middleware import RequestContextMiddleware
from .api.v1.platform import router as platform_router
from .settings import Settings, get_settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info("edge.started", env=settings.env)
    try:
        yield
    finally:
        log.info("edge.stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Origo Edge API",
        version="1.0.0",
        description="Control plane for PQC-secured satellite key management.",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs" if settings.env != "prod" else None,
        redoc_url=None,
        root_path=settings.api_root_path,
        lifespan=lifespan,
        generate_unique_id_function=lambda route: f"{'_'.join(route.tags) if route.tags else 'route'}_{route.name}",
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )

    install_exception_handlers(app)
    app.include_router(platform_router)

    @app.get("/v1/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
