"""Design §3.3.1's Sync Client endpoints. Device-authenticated (see require_edge_token
in deps.py), never OIDC — this is a machine caller, not a dashboard user.

JobPlan compilation and KMS signing (design §8.3) aren't built yet — plans returned
here are unsigned placeholders with signature=b"". station-agent's model validator
doesn't check the signature today either, so this runs end to end locally; treat an
empty signature as "not yet wired for real deployment," not "secure."
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from ...repositories.job import JobRepository
from ..deps import get_job_repo, require_edge_token

router = APIRouter(prefix="/v1/edge", tags=["edge"], dependencies=[Depends(require_edge_token)])


@router.get("/stations/{station_ref}/job-plans")
async def get_job_plans(station_ref: str, jobs: Annotated[JobRepository, Depends(get_job_repo)]) -> dict[str, object]:
    import uuid as _uuid

    scheduled = await jobs.list(states=None)  # station_device_id filter: see note below
    now = datetime.now(UTC)
    items = [
        {
            "plan_id": str(_uuid.uuid4()),
            "ground_station_id": station_ref,
            "pass_id": str(_uuid.uuid4()),
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(minutes=15)).isoformat(),
            "steps": [
                {
                    "step_id": str(_uuid.uuid4()), "job_id": str(job.id), "job_type": job.type.value,
                    "expected_start_offset_sec": 0, "timeout_sec": 300,
                    "parameters": job.parameters | ({"channel_set_ref": "cs-s-band"} if job.type.value == "KEY_EXCHANGE" else {}),
                }
                for job in scheduled if job.state.value == "SCHEDULED"
            ],
            "signature": "", "signed_payload": "",
        }
    ]
    return {"items": items}


@router.post("/stations/{station_ref}/status", status_code=204)
async def push_status(station_ref: str, body: dict[str, object]) -> None:
    """Fan-out by event type belongs here once telemetry/audit tables exist (§4.2's
    Telemetry Ingestion, Audit Log). For now this accepts and logs — enough for
    station-agent's push_status() to succeed rather than error every sync cycle."""
    import structlog

    structlog.get_logger(__name__).info("edge.status_received", station_ref=station_ref, event_count=len(body.get("events", [])))