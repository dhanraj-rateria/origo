from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...repositories.telemetry import TelemetryRepository
from ..deps import get_telemetry_repo


router = APIRouter(prefix="/v1", tags=["telemetry"])


class TelemetryCreate(BaseModel):
    source_device_id: uuid.UUID
    recorded_at: datetime
    metric_type: str
    value: dict


@router.get("/telemetry")
async def list_telemetry(
    telemetry: Annotated[
        TelemetryRepository,
        Depends(get_telemetry_repo),
    ],
    source_device_id: uuid.UUID | None = None,
    metric_type: str | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "id": str(record.id),
            "source_device_id": str(record.source_device_id),
            "recorded_at": record.recorded_at.isoformat(),
            "metric_type": record.metric_type,
            "value": record.value,
        }
        for record in await telemetry.list(
            source_device_id=source_device_id,
            metric_type=metric_type,
        )
    ]


@router.get("/telemetry/{telemetry_id}")
async def get_telemetry(
    telemetry_id: uuid.UUID,
    telemetry: Annotated[
        TelemetryRepository,
        Depends(get_telemetry_repo),
    ],
) -> dict[str, object]:
    record = await telemetry.get(telemetry_id)

    if record is None:
        raise HTTPException(404, detail="Telemetry record not found")

    return {
        "id": str(record.id),
        "source_device_id": str(record.source_device_id),
        "recorded_at": record.recorded_at.isoformat(),
        "metric_type": record.metric_type,
        "value": record.value,
    }


@router.post("/telemetry", status_code=201)
async def create_telemetry(
    body: TelemetryCreate,
    telemetry: Annotated[
        TelemetryRepository,
        Depends(get_telemetry_repo),
    ],
) -> dict[str, object]:
    record = await telemetry.create(
        source_device_id=body.source_device_id,
        recorded_at=body.recorded_at,
        metric_type=body.metric_type,
        value=body.value,
    )

    return {
        "id": str(record.id),
        "source_device_id": str(record.source_device_id),
        "recorded_at": record.recorded_at.isoformat(),
        "metric_type": record.metric_type,
        "value": record.value,
    }