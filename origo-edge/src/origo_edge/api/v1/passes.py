from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...repositories.pass_ import PassRepository
from ..deps import get_pass_repo


router = APIRouter(prefix="/v1", tags=["passes"])


class PassCreate(BaseModel):
    satellite_device_id: uuid.UUID
    ground_device_id: uuid.UUID
    aos: datetime
    los: datetime
    max_elevation_deg: float | None = None
    band: str


@router.get("/passes")
async def list_passes(
    passes: Annotated[PassRepository, Depends(get_pass_repo)],
    satellite_device_id: uuid.UUID | None = None,
    ground_device_id: uuid.UUID | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "id": str(device_pass.id),
            "satellite_device_id": str(device_pass.satellite_device_id),
            "ground_device_id": str(device_pass.ground_device_id),
            "aos": device_pass.aos.isoformat(),
            "los": device_pass.los.isoformat(),
            "max_elevation_deg": device_pass.max_elevation_deg,
            "band": device_pass.band,
        }
        for device_pass in await passes.list(
            satellite_device_id=satellite_device_id,
            ground_device_id=ground_device_id,
        )
    ]


@router.get("/passes/{pass_id}")
async def get_pass(
    pass_id: uuid.UUID,
    passes: Annotated[PassRepository, Depends(get_pass_repo)],
) -> dict[str, object]:
    device_pass = await passes.get(pass_id)

    if device_pass is None:
        raise HTTPException(404, detail="Pass not found")

    return {
        "id": str(device_pass.id),
        "satellite_device_id": str(device_pass.satellite_device_id),
        "ground_device_id": str(device_pass.ground_device_id),
        "aos": device_pass.aos.isoformat(),
        "los": device_pass.los.isoformat(),
        "max_elevation_deg": device_pass.max_elevation_deg,
        "band": device_pass.band,
    }


@router.post("/passes", status_code=201)
async def create_pass(
    body: PassCreate,
    passes: Annotated[PassRepository, Depends(get_pass_repo)],
) -> dict[str, object]:
    if body.los <= body.aos:
        raise HTTPException(
            400,
            detail="los must be later than aos",
        )

    device_pass = await passes.create(
        satellite_device_id=body.satellite_device_id,
        ground_device_id=body.ground_device_id,
        aos=body.aos,
        los=body.los,
        max_elevation_deg=body.max_elevation_deg,
        band=body.band,
    )

    return {
        "id": str(device_pass.id),
        "satellite_device_id": str(device_pass.satellite_device_id),
        "ground_device_id": str(device_pass.ground_device_id),
        "aos": device_pass.aos.isoformat(),
        "los": device_pass.los.isoformat(),
        "max_elevation_deg": device_pass.max_elevation_deg,
        "band": device_pass.band,
    }