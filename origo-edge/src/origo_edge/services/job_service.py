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

    async def create_data_delivery(
        self, *, satellite_device_id: uuid.UUID, ground_device_id: uuid.UUID,
        kem_param_set: KemParamSet = KemParamSet.ML_KEM_1024,
    ) -> Job:
        """A DATA_DELIVERY job rides on the pair's current ACTIVE key.

        If one already exists, this is exactly what it was before: resolve it now,
        attach both identifiers a job actually needs (see the note below), done.

        If none exists, this used to raise PolicyViolation and make the caller run a
        key exchange first. It now auto-triggers one instead — but a key exchange
        doesn't complete synchronously (it finishes on a separate pass, potentially a
        separate poll cycle, after station-agent actually runs it), so this job is
        created *unresolved* (key_id=None, parameters={}) rather than blocked.
        Resolution happens lazily in edge.py's get_job_plans, on every poll, once a
        key for this pair actually goes ACTIVE — see that function's own comment for
        why it has to happen there and not here.

        Known limitation: if the auto-triggered key exchange itself fails, this job
        just stays SCHEDULED forever, silently retried every poll with nothing
        visible telling the operator why. Not fixed here — would need either an
        expiry or a way to propagate one job's failure onto a dependent job, and I'm
        not guessing at job_lifecycle.py's state machine to build that blind.

        Two different identifiers get attached once resolved, deliberately not the
        same one: job.key_id is the Postgres Key row's UUID (what the rest of
        origo-edge reasons about). parameters["key_id"] is Origo Terrestrial's own
        hsm_key_reference string (e.g. "key-fef10ac3018a") — the value
        pass_executor.py's _run_data_delivery reads out of the JobPlanStep and hands
        to DecryptPayload, since that's what OrigoTerrestrialServicer's _active_keys
        dict is actually keyed by, not the database UUID. Attaching the wrong one
        here reproduces the exact "unknown key_id" rejection this whole feature
        exists to avoid.
        """
        candidates = await self._key_service.get_active_for_pair(
            satellite_device_id=satellite_device_id, ground_device_id=ground_device_id,
        )
        if candidates:
            key = candidates[0]   # the DB partial unique index guarantees at most one
            return await self._jobs.create(
                type=JobType.DATA_DELIVERY, satellite_device_id=satellite_device_id,
                ground_device_id=ground_device_id, key_id=key.id,
                parameters={"key_id": key.hsm_key_reference},
            )

        try:
            await self.create_key_exchange(
                satellite_device_id=satellite_device_id, ground_device_id=ground_device_id,
                kem_param_set=kem_param_set,
            )
        except PolicyViolation:
            # create_pending's own in-flight guard rejected this — a key exchange
            # for this pair is already running. That's fine: this data-delivery job
            # will pick up whatever key that one produces, same as if it triggered
            # a fresh one itself.
            pass

        return await self._jobs.create(
            type=JobType.DATA_DELIVERY, satellite_device_id=satellite_device_id,
            ground_device_id=ground_device_id, key_id=None, parameters={},
        )

    async def get(self, job_id: uuid.UUID) -> Job:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFound("job", job_id)
        return job

    async def list(self) -> list[Job]:
        return await self._jobs.list()