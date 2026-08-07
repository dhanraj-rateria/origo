from __future__ import annotations

import uuid
from typing import Annotated
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from ...domain.enums import DeviceStatus, DeviceType
from ...repositories.device import DeviceRepository
from ..deps import get_device_repo

router = APIRouter(prefix="/v1", tags=["devices"])

class DeviceCreate(BaseModel):
    name: str
    type: DeviceType
    serial_number: str
    mission: str | None = None

@router.get("/devices")
async def list_devices(devices: Annotated[DeviceRepository, Depends(get_device_repo)]) -> list[dict[str, object]]:
    return [
        {
            "id": str(d.id), "name": d.name, "type": d.type.value, "mission": d.mission,
            "status": d.status.value, "last_contact": d.last_contact_at.isoformat() if d.last_contact_at else None,
        }
        for d in await devices.list()
    ]


@router.post("/devices", status_code=201)
async def register_device(
    body: DeviceCreate, devices: Annotated[DeviceRepository, Depends(get_device_repo)],
) -> dict[str, object]:
    if await devices.get_by_serial(body.serial_number) is not None:
        raise HTTPException(409, detail=f"serial_number '{body.serial_number}' is already registered")
    device = await devices.create(
        name=body.name, type=body.type, serial_number=body.serial_number,
        mission=body.mission, status=DeviceStatus.ACTIVE,
    )
    return {"id": str(device.id), "name": device.name, "type": device.type.value}