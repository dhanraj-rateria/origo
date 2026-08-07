# services/job_service.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.job import Job
from ..domain.enums import JobType
from ..domain.errors import NotFound
from ..repositories.job import JobRepository
from .key_service import KeyService
from ..domain.enums import KemParamSet


class JobService:
    def __init__(self, *, session: AsyncSession, jobs: JobRepository, keys: KeyService) -> None:
        self._session, self._jobs, self._key_service = session, jobs, keys

    async def create_key_exchange(
        self, *, satellite_device_id: uuid.UUID, ground_device_id: uuid.UUID, kem_param_set: KemParamSet,
    ) -> Job:
        """Design §5.2's correction still holds: this creates a *record* the Platform
        tracks. Delivering the resulting policy to the Module is the JobPlan/edge path
        below — this call never talks to hardware directly."""
        key = await self._key_service.create_pending(
            satellite_device_id=satellite_device_id, ground_device_id=ground_device_id, kem_param_set=kem_param_set,
        )
        return await self._jobs.create(
            type=JobType.KEY_EXCHANGE, satellite_device_id=satellite_device_id,
            ground_device_id=ground_device_id, key_id=key.id,
            parameters={"kem_param_set": kem_param_set.value},
        )

    async def create_data_delivery(self, *, satellite_device_id: uuid.UUID, ground_device_id: uuid.UUID) -> Job:
        return await self._jobs.create(
            type=JobType.DATA_DELIVERY, satellite_device_id=satellite_device_id, ground_device_id=ground_device_id,
        )

    async def get(self, job_id: uuid.UUID) -> Job:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFound("job", job_id)
        return job