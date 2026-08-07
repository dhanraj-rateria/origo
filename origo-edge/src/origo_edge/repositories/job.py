# repositories/job.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.job import Job
from ..domain.enums import JobState


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, job_id: uuid.UUID) -> Job | None:
        return await self._session.get(Job, job_id)

    async def list(self, *, station_device_id: uuid.UUID | None = None, states: list[JobState] | None = None) -> list[Job]:
        stmt = select(Job).order_by(Job.created_at.desc())
        if station_device_id is not None:
            stmt = stmt.where(Job.ground_device_id == station_device_id)
        if states:
            stmt = stmt.where(Job.state.in_(states))
        return list((await self._session.execute(stmt)).scalars())

    async def create(self, **fields: object) -> Job:
        job = Job(**fields)
        self._session.add(job)
        await self._session.flush()
        return job