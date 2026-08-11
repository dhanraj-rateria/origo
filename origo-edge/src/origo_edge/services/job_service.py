# services/job_service.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.job import Job
from ..domain.enums import JobType
from ..domain.errors import NotFound, PolicyViolation
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
        """A DATA_DELIVERY job rides on the pair's current ACTIVE key — an operator
        creating this job (through the platform, or the API directly) shouldn't need
        to know an internal key identifier to do it, so it's resolved here rather
        than accepted as input.

        Two different identifiers get attached, deliberately not the same one:
        job.key_id is the Postgres Key row's UUID (what this service, and the rest
        of origo-edge, already reasons about). parameters["key_id"] is Origo
        Terrestrial's own hsm_key_reference string (e.g. "key-fef10ac3018a") — the
        value pass_executor.py's _run_data_delivery reads out of the JobPlanStep and
        hands to DecryptPayload, since that's what OrigoTerrestrialServicer's
        _active_keys dict is actually keyed by, not the database UUID. Attaching the
        wrong one here reproduces the exact "unknown key_id" rejection this fixes.
        """
        candidates = await self._key_service.get_active_for_pair(
            satellite_device_id=satellite_device_id, ground_device_id=ground_device_id,
        )
        if not candidates:
            raise PolicyViolation(
                "no ACTIVE key for this device pair — run a key exchange and wait for it to "
                "complete before requesting a data delivery"
            )
        key = candidates[0]   # the DB partial unique index guarantees at most one
        if not key.hsm_key_reference:
            # Shouldn't happen once a key is genuinely ACTIVE (KeyService.advance
            # only sets ACTIVE alongside hsm_key_reference), but a job that
            # silently can't be executed is worse than one that fails loudly here.
            raise PolicyViolation(f"key {key.id} is ACTIVE but has no hsm_key_reference recorded")

        return await self._jobs.create(
            type=JobType.DATA_DELIVERY, satellite_device_id=satellite_device_id,
            ground_device_id=ground_device_id, key_id=key.id,
            parameters={"key_id": key.hsm_key_reference},
        )

    async def get(self, job_id: uuid.UUID) -> Job:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFound("job", job_id)
        return job

    async def list(self) -> list[Job]:
        return await self._jobs.list()
