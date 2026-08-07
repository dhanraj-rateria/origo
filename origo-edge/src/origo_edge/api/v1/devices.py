from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from ...domain.enums import DeviceStatus, DeviceType
from ...repositories.device import DeviceRepository
from ..deps import get_device_repo

router = APIRouter(prefix="/v1", tags=["devices"])


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
    body: dict[str, str], devices: Annotated[DeviceRepository, Depends(get_device_repo)],
) -> dict[str, object]:
    """Minimal registration for local dev/seeding. Design §8.3: real registration is
    the last step of a provisioning ceremony, not an open call — this is a placeholder
    to seed a working local database, not the production endpoint."""
    device = await devices.create(
        name=body["name"], type=DeviceType(body["type"]), mission=body.get("mission"),
        status=DeviceStatus.ACTIVE,
    )
    return {"id": str(device.id), "name": device.name, "type": device.type.value}