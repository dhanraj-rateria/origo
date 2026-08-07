from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..repositories.device import DeviceRepository
from ..repositories.job import JobRepository
from ..repositories.key import KeyRepository
from ..services.job_service import JobService
from ..services.key_service import KeyService
from ..settings import Settings

DbSession = Annotated[AsyncSession, Depends(get_session)]


def get_device_repo(session: DbSession) -> DeviceRepository:
    return DeviceRepository(session)


def get_key_repo(session: DbSession) -> KeyRepository:
    return KeyRepository(session)


def get_job_repo(session: DbSession) -> JobRepository:
    return JobRepository(session)


def get_key_service(
    session: DbSession,
    keys: Annotated[KeyRepository, Depends(get_key_repo)],
    devices: Annotated[DeviceRepository, Depends(get_device_repo)],
) -> KeyService:
    return KeyService(session=session, keys=keys, devices=devices)


def get_job_service(
    session: DbSession,
    jobs: Annotated[JobRepository, Depends(get_job_repo)],
    key_service: Annotated[KeyService, Depends(get_key_service)],
) -> JobService:
    return JobService(session=session, jobs=jobs, keys=key_service)


def require_edge_token(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    """Dev-only stand-in for design §8.1's mTLS device auth: a single shared bearer
    token from settings, checked with constant-time comparison. Real deployments
    replace this with the client-certificate check the design calls for — swapping it
    out later doesn't touch anything in edge.py, since the route only depends on this
    function raising or not."""
    import hmac

    settings: Settings = request.app.state.settings
    expected = f"Bearer {settings.edge_device_token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid or missing device token")