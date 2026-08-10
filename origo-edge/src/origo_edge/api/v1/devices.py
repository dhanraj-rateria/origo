from __future__ import annotations

import uuid
from typing import Annotated
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from ...domain.enums import DeviceStatus, DeviceType
from ...repositories.device import DeviceRepository
from ...services.device_provisioner import DeviceProvisioner
from ..deps import get_device_provisioner, get_device_repo

router = APIRouter(prefix="/v1", tags=["devices"])

class DeviceCreate(BaseModel):
    name: str
    type: DeviceType
    serial_number: str
    mission: str | None = None
    # Which already-registered device (by serial_number) this one exchanges keys
    # with. Required for ORIGO_TERRESTRIAL if the Docker device-loop provisioner is
    # enabled (it needs to know which Origo Space container to pair with); ignored
    # otherwise. See docs/docker-device-loop.md.
    peer_serial_number: str | None = None

@router.get("/devices")
async def list_devices(devices: Annotated[DeviceRepository, Depends(get_device_repo)]) -> list[dict[str, object]]:
    return [
        {
            "id": str(d.id), "name": d.name, "type": d.type.value, "mission": d.mission,
            "status": d.status.value, "peer_serial_number": d.peer_serial_number,
            "last_contact": d.last_contact_at.isoformat() if d.last_contact_at else None,
        }
        for d in await devices.list()
    ]


@router.post("/devices", status_code=201)
async def register_device(
    body: DeviceCreate,
    devices: Annotated[DeviceRepository, Depends(get_device_repo)],
    provisioner: Annotated[DeviceProvisioner, Depends(get_device_provisioner)],
) -> dict[str, object]:
    if await devices.get_by_serial(body.serial_number) is not None:
        raise HTTPException(409, detail=f"serial_number '{body.serial_number}' is already registered")
    device = await devices.create(
        name=body.name, type=body.type, serial_number=body.serial_number,
        mission=body.mission, peer_serial_number=body.peer_serial_number, status=DeviceStatus.ACTIVE,
    )

    # Best-effort local-dev container provisioning (see DeviceProvisioner's own
    # docstring) — never lets a Docker/provisioning problem fail the registration
    # itself; the device row stands regardless, same as it always has.
    container_status = "not_provisioned"
    if provisioner.enabled:
        try:
            provisioner.provision(
                device_type=body.type, serial_number=body.serial_number,
                peer_serial_number=body.peer_serial_number,
            )
            container_status = "running"
        except Exception:  # noqa: BLE001 — provisioning failures are reported, not raised
            container_status = "provisioning_failed"

    return {
        "id": str(device.id), "name": device.name, "type": device.type.value,
        "container_status": container_status,
    }
