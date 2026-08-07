from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...domain.enums import JobType, KemParamSet
from ...services.job_service import JobService
from ..deps import get_job_service

router = APIRouter(prefix="/v1", tags=["jobs"])


class JobCreate(BaseModel):
    type: JobType
    satellite_device_id: uuid.UUID
    ground_device_id: uuid.UUID
    kem_param_set: KemParamSet = KemParamSet.ML_KEM_1024


def _job_out(job) -> dict[str, object]:  # noqa: ANN001
    return {
        "id": str(job.id), "type": job.type.value.lower(), "state": job.state.value.lower(),
        "satellite_device_id": str(job.satellite_device_id), "ground_device_id": str(job.ground_device_id),
        "key_id": str(job.key_id) if job.key_id else None, "created": job.created_at.isoformat(),
    }


@router.get("/jobs")
async def list_jobs(jobs: Annotated[JobService, Depends(get_job_service)]) -> list[dict[str, object]]:
    return [_job_out(j) for j in await jobs.list()]

@router.post("/jobs", status_code=202)
async def create_job(body: JobCreate, jobs: Annotated[JobService, Depends(get_job_service)]) -> dict[str, object]:
    if body.type is JobType.KEY_EXCHANGE:
        job = await jobs.create_key_exchange(
            satellite_device_id=body.satellite_device_id, ground_device_id=body.ground_device_id,
            kem_param_set=body.kem_param_set,
        )
    else:
        job = await jobs.create_data_delivery(
            satellite_device_id=body.satellite_device_id, ground_device_id=body.ground_device_id,
        )
    return _job_out(job)


@router.get("/jobs/{job_id}")
async def get_job(job_id: uuid.UUID, jobs: Annotated[JobService, Depends(get_job_service)]) -> dict[str, object]:
    return _job_out(await jobs.get(job_id))