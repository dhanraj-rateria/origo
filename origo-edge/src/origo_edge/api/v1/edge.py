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
    keys: Annotated[KeyService, Depends(get_key_service)],
) -> dict[str, object]:
    station = await devices.get_by_serial(station_ref)
    if station is None or station.type is not DeviceType.ORIGO_TERRESTRIAL:
        return {"items": []}

    scheduled = await jobs.list(station_device_id=station.id, states=[JobState.SCHEDULED])
    now = datetime.now(UTC)

    steps = []
    for job in scheduled:
        if job.type is JobType.DATA_DELIVERY and job.key_id is None:
            # JobService.create_data_delivery auto-triggers a key exchange and
            # creates this job unresolved when no ACTIVE key existed yet at request
            # time. Resolved here, on every poll, rather than at creation, because
            # the key exchange this depends on completes asynchronously — a
            # separate pass, possibly a separate poll cycle — after this job
            # already exists in Postgres. A GET route mutating rows is unusual;
            # it's deliberate: same request, same session, a pure "resolve once and
            # remember" backfill, not a state transition anything else needs to
            # arbitrate.
            candidates = await keys.get_active_for_pair(
                satellite_device_id=job.satellite_device_id, ground_device_id=job.ground_device_id,
            )
            if not candidates:
                continue   # still waiting on the key exchange — try again next poll
            active_key = candidates[0]
            job.key_id = active_key.id
            job.parameters = {**job.parameters, "key_id": active_key.hsm_key_reference}

        steps.append({
            "step_id": str(uuid.uuid4()), "job_id": str(job.id), "job_type": job.type.value,
            "expected_start_offset_sec": 0, "timeout_sec": 300,
            "parameters": job.parameters | ({"channel_set_ref": "cs-s-band"} if job.type is JobType.KEY_EXCHANGE else {}),
        })

    items = [{
        "plan_id": str(uuid.uuid4()), "ground_station_id": station_ref,
        "pass_id": str(uuid.uuid4()), "valid_from": now.isoformat(),
        "valid_until": (now + timedelta(minutes=15)).isoformat(),
        "steps": steps,
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
                # Design §4's handshake reaches origo-edge as exactly one ground-side
                # event at pass end — there's no separate signal for "ek sent" or "ct
                # received" as their own moments, so walk KEY_MACHINE through every
                # intermediate hop here rather than widening it to allow a direct
                # PENDING_KEYGEN -> ACTIVE jump. hsm_key_reference is only actually
                # written on the final ACTIVE hop — see KeyService.advance's own
                # `if target is KeyState.ACTIVE:` gate — so passing it on all four
                # calls is harmless.
                for target in (KeyState.EK_SENT, KeyState.AWAITING_CT, KeyState.DECAPS_COMPLETE, KeyState.ACTIVE):
                    await keys.advance(key_id=job.key_id, target=target, hsm_key_reference=detail.get("key_id"))
            elif outcome == "FAILED":
                job.failure_reason = detail.get("reason")
                # A rejected signature (or any other definite FAILED cause) doesn't
                # improve on retry with the same key — and KeyService.create_pending's
                # in-flight guard blocks a *new* key exchange for this device pair for
                # as long as this one sits in PENDING_KEYGEN. Revoke it so the pair
                # isn't stuck forever. advance() never checks requires_dual_control —
                # confirmed nothing in its body references it — so this
                # system-initiated revoke needs nothing extra.
                await keys.advance(key_id=job.key_id, target=KeyState.REVOKED)
            elif outcome == "TIMED_OUT":
                job.failure_reason = detail.get("reason")
                # Deliberately NOT revoked: a pass ending before the ek arrived
                # doesn't mean the key is bad, just that this pass didn't carry it —
                # leave it PENDING_KEYGEN so a later pass can retry the same key
                # exchange.