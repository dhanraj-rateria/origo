"""Design §3.3.1's Sync Client endpoints. Device-authenticated (require_edge_token —
dev-only stand-in for the design's mTLS)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
import base64
from fastapi import APIRouter, Depends

from ...domain.enums import DeviceType, JobState, JobType, KeyState
from ...repositories.device import DeviceRepository
from ...repositories.job import JobRepository
from ...services.key_service import KeyService
from ..deps import get_device_repo, get_job_repo, get_key_service, require_edge_token

router = APIRouter(prefix="/v1/edge", tags=["edge"], dependencies=[Depends(require_edge_token)])

_OUTCOME_TO_STATE = {"ACTIVE": JobState.ACTIVE, "FAILED": JobState.FAILED, "TIMED_OUT": JobState.TIMED_OUT}


@router.get("/stations/{station_ref}/job-plans")
async def get_job_plans(
    station_ref: str,
    jobs: Annotated[JobRepository, Depends(get_job_repo)],
    devices: Annotated[DeviceRepository, Depends(get_device_repo)],
) -> dict[str, object]:
    station = await devices.get_by_serial(station_ref)
    if station is None or station.type is not DeviceType.ORIGO_TERRESTRIAL:
        return {"items": []}

    scheduled = await jobs.list(station_device_id=station.id, states=[JobState.SCHEDULED])
    now = datetime.now(UTC)
    items = [{
        "plan_id": str(uuid.uuid4()), "ground_station_id": station_ref,
        "pass_id": str(uuid.uuid4()), "valid_from": now.isoformat(),
        "valid_until": (now + timedelta(minutes=15)).isoformat(),
        "steps": [{
            "step_id": str(uuid.uuid4()), "job_id": str(job.id), "job_type": job.type.value,
            "expected_start_offset_sec": 0, "timeout_sec": 300,
            "parameters": job.parameters | ({"channel_set_ref": "cs-s-band"} if job.type is JobType.KEY_EXCHANGE else {}),
        } for job in scheduled],
        "signature": "", "signed_payload": "",
    }]
    return {"items": items}


@router.post("/stations/{station_ref}/status", status_code=204)
async def push_status(
    station_ref: str, body: dict[str, object],
    jobs: Annotated[JobRepository, Depends(get_job_repo)],
    keys: Annotated[KeyService, Depends(get_key_service)],
) -> None:
    """Fans job.result events out to Job/Key state. Everything else (raw telemetry,
    audit-log events) still just needs a table to land in — the fan-out shape here is
    the pattern to repeat once TelemetryRecord/AuditEvent exist."""
    for event in body.get("events", []):
        if event.get("event_type") != "job.result":
            continue
        job = await jobs.get(uuid.UUID(event["job_id"]))
        if job is None:
            continue

        outcome = event["outcome"]
        detail = event.get("detail", {})
        job.state = _OUTCOME_TO_STATE.get(outcome, job.state)

        if job.type is JobType.DATA_DELIVERY and "plaintext_b64" in detail:
            # Interim home for the decrypted payload — a dedicated results table or
            # object-store reference is the real answer once volumes grow past
            # "comfortably fits in a JSONB column."
            job.parameters = job.parameters | {
                "result_bytes_b64": detail["plaintext_b64"],
                "result_frame_count": detail.get("frame_count"),
            }

        if job.type is JobType.KEY_EXCHANGE and job.key_id:
            if outcome == "ACTIVE":
                await keys.advance(key_id=job.key_id, target=KeyState.ACTIVE, hsm_key_reference=detail.get("key_id"))
            elif outcome in {"FAILED", "TIMED_OUT"}:
                job.failure_reason = detail.get("reason")