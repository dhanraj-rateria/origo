from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["platform"])


@router.get("/overview")
async def overview() -> dict[str, int]:
    return {
        "satellites": 3,
        "ground_stations": 2,
        "active_keys": 5,
        "open_alerts": 2,
    }


@router.get("/devices")
async def devices() -> list[dict[str, str]]:
    return [
        {"id": "dev-001", "name": "Aster-1", "type": "Satellite", "mission": "Asteroid survey", "status": "Active", "last_contact": "2m ago"},
        {"id": "dev-002", "name": "GS-North", "type": "Ground station", "mission": "Primary TT&C", "status": "Active", "last_contact": "10m ago"},
    ]


@router.get("/passes")
async def passes() -> list[dict[str, str]]:
    return [
        {"reservation_token": "tok-001", "satellite": "Aster-1", "ground_station": "GS-North", "band": "S-band", "aos": "2026-08-06T09:15:00Z", "los": "2026-08-06T09:23:00Z", "elevation": "47.2°"},
        {"reservation_token": "tok-002", "satellite": "Aster-2", "ground_station": "GS-South", "band": "X-band", "aos": "2026-08-06T10:10:00Z", "los": "2026-08-06T10:20:00Z", "elevation": "61.8°"},
    ]


@router.get("/jobs")
async def jobs() -> list[dict[str, str]]:
    return [
        {"id": "job-001", "type": "key", "route": "Aster-1 → GS-North", "state": "active", "created": "11m ago"},
        {"id": "job-002", "type": "data", "route": "Aster-2 → GS-South", "state": "scheduled", "created": "38m ago"},
    ]


@router.get("/keys")
async def keys() -> list[dict[str, str]]:
    return [
        {"id": "KEY-8830", "route": "Aster-1 → GS-North", "parameter_set": "ML-KEM-1024", "state": "Active", "created": "2h ago"},
        {"id": "KEY-8829", "route": "Aster-2 → GS-South", "parameter_set": "ML-KEM-768", "state": "Superseded", "created": "5h ago"},
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
