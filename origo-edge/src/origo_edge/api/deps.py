from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..repositories.alert import AlertRepository
from ..repositories.device import DeviceRepository
from ..repositories.job import JobRepository
from ..repositories.key import KeyRepository
from ..repositories.pass_repository import PassRepository
from ..repositories.telemetry import TelemetryRepository
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


def get_alert_repo(session: DbSession) -> AlertRepository:
    return AlertRepository(session)


def get_pass_repo(session: DbSession) -> PassRepository:
    return PassRepository(session)


def get_telemetry_repo(session: DbSession) -> TelemetryRepository:
    return TelemetryRepository(session)


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


def require_edge_token(request: Request) -> None:
    """mTLS device auth.

    Requires the reverse proxy/ASGI server terminating TLS to forward the
    verified client cert's CN.
    """
    cn = request.headers.get("X-Client-CN")

    if not cn:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="no client certificate presented",
        )

    request.state.device_cn = cn