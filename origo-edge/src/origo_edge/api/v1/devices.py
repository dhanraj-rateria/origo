from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

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


def _device_dict(d) -> dict[str, object]:
    return {
        "id": str(d.id), "name": d.name, "type": d.type.value, "mission": d.mission,
        "status": d.status.value, "peer_serial_number": d.peer_serial_number,
        # Docker device-loop only — see the model column's own docstring. Always
        # None for a real device or when provisioning is disabled; the UI's job is
        # to treat that as "no provisioning info," not "device unhealthy."
        "provisioning_status": d.provisioning_status,
        "deleted_at": d.deleted_at.isoformat() if d.deleted_at else None,
        "last_contact": d.last_contact_at.isoformat() if d.last_contact_at else None,
    }


@router.get("/devices")
async def list_devices(
    devices: Annotated[DeviceRepository, Depends(get_device_repo)],
    deleted: bool = False,
) -> list[dict[str, object]]:
    """deleted=false (default) is the active fleet view; deleted=true shows only
    soft-deleted devices. Filtered in Python, not pushed into the repository query —
    same reasoning as keys.py's revoked filter: repositories/device.py wasn't
    available to add a variant to, and this doesn't need to scale further than a
    demo fleet."""
    all_devices = await devices.list()
    filtered = [d for d in all_devices if (d.deleted_at is not None) == deleted]
    return [_device_dict(d) for d in filtered]


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
    #
    # run_in_threadpool: provision() is synchronous and does real blocking I/O
    # (docker SDK calls, httpx.Client requests, and time.sleep() retry loops — up
    # to ~50s worst case across both containers a Terrestrial registration
    # starts). Calling it directly here would stall this whole process's single
    # event loop for that entire duration, blocking every other concurrent
    # request to origo-edge.
    if provisioner.enabled:
        try:
            await run_in_threadpool(
                provisioner.provision,
                device_type=body.type, serial_number=body.serial_number,
                peer_serial_number=body.peer_serial_number,
            )
            device.provisioning_status = "running"
        except Exception:  # noqa: BLE001 — provisioning failures are reported, not raised
            device.provisioning_status = "provisioning_failed"
    else:
        device.provisioning_status = None

    return _device_dict(device)


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: uuid.UUID,
    devices: Annotated[DeviceRepository, Depends(get_device_repo)],
    provisioner: Annotated[DeviceProvisioner, Depends(get_device_provisioner)],
) -> None:
    """Soft-delete: stops and removes the device's Docker device-loop container(s)
    (best-effort — never blocks the rest of this on a Docker problem), then marks
    the row deleted_at rather than removing it. No foreign-key concerns at all this
    way — every job and key that references this device's id keeps resolving fine,
    and any other device's peer_serial_number still finds this row via
    get_by_serial. Idempotent: deleting an already-deleted device is a silent no-op,
    not an error.

    No restore flow exists — deleted_at, once set, is never cleared by anything in
    this codebase.
    """
    device = await devices.get(device_id)
    if device is None:
        raise HTTPException(404, detail=f"device {device_id} not found")
    if device.deleted_at is not None:
        return

    if provisioner.enabled:
        try:
            await run_in_threadpool(
                provisioner.deprovision, serial_number=device.serial_number, device_type=device.type,
            )
            device.provisioning_status = "deleted"
        except Exception:  # noqa: BLE001 — container cleanup is best-effort; the
            pass            # deletion below proceeds regardless of whether it worked.

    device.deleted_at = datetime.now(UTC)