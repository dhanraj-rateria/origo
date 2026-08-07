from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...domain.enums import DeviceType, KeyState
from ...repositories.device import DeviceRepository
from ...repositories.key import KeyRepository
from ..deps import get_device_repo, get_key_repo

router = APIRouter(prefix="/v1", tags=["platform"])


@router.get("/overview")
async def overview(
    devices: Annotated[DeviceRepository, Depends(get_device_repo)],
    keys: Annotated[KeyRepository, Depends(get_key_repo)],
) -> dict[str, int]:
    all_devices = await devices.list()
    all_keys = await keys.list()
    return {
        "satellites": sum(1 for d in all_devices if d.type is DeviceType.ORIGO_SPACE),
        "ground_stations": sum(1 for d in all_devices if d.type is DeviceType.ORIGO_TERRESTRIAL),
        "active_keys": sum(1 for k in all_keys if k.state is KeyState.ACTIVE),
        "open_alerts": 2,  # unchanged — alerts table doesn't exist yet
    }

@router.get("/passes")
async def passes() -> list[dict[str, str]]:
    return [
        {"reservation_token": "tok-001", "satellite": "Aster-1", "ground_station": "GS-North", "band": "S-band", "aos": "2026-08-06T09:15:00Z", "los": "2026-08-06T09:23:00Z", "elevation": "47.2°"},
        {"reservation_token": "tok-002", "satellite": "Aster-2", "ground_station": "GS-South", "band": "X-band", "aos": "2026-08-06T10:10:00Z", "los": "2026-08-06T10:20:00Z", "elevation": "61.8°"},
    ]


@router.get("/telemetry")
async def telemetry() -> list[dict[str, str]]:
    return [
        {"name": "Module A", "temperature": "24°C", "tamper": "Nominal", "self_test": "Pass"},
        {"name": "Ground HSM", "temperature": "29°C", "tamper": "Nominal", "self_test": "Pass"},
    ]


@router.get("/policies")
async def policies() -> list[dict[str, str]]:
    return [
        {"name": "Aster default", "mission": "Aster constellation", "trigger": "Pass-based", "parameter_set": "ML-KEM-1024", "value": "Every pass"},
    ]


@router.get("/alerts")
async def alerts() -> list[dict[str, str]]:
    return [
        {"id": "alert-001", "severity": "Warning", "device": "Aster-1", "condition": "Entropy health below threshold", "state": "Open", "opened": "11m ago"},
        {"id": "alert-002", "severity": "Info", "device": "GS-North", "condition": "HSM self-test passed", "state": "Acknowledged", "opened": "1h ago"},
    ]


@router.get("/audit")
async def audit() -> list[dict[str, str]]:
    return [
        {"event": "KEYGEN", "device": "Aster-1", "actor": "ops", "time": "2026-08-06T09:12:00Z"},
        {"event": "CONFIG_PUSH", "device": "GS-North", "actor": "platform", "time": "2026-08-06T09:08:00Z"},
    ]
