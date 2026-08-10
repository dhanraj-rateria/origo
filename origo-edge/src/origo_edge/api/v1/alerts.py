from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...repositories.alert import AlertRepository
from ..deps import get_alert_repo


router = APIRouter(prefix="/v1", tags=["alerts"])


class AlertCreate(BaseModel):
    device_id: uuid.UUID
    severity: str
    condition: str
    state: str = "OPEN"


@router.get("/alerts")
async def list_alerts(
    alerts: Annotated[AlertRepository, Depends(get_alert_repo)],
    device_id: uuid.UUID | None = None,
    severity: str | None = None,
    state: str | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "id": str(alert.id),
            "device_id": str(alert.device_id),
            "severity": alert.severity,
            "condition": alert.condition,
            "state": alert.state,
            "created_at": alert.created_at.isoformat(),
        }
        for alert in await alerts.list(
            device_id=device_id,
            severity=severity,
            state=state,
        )
    ]


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: uuid.UUID,
    alerts: Annotated[AlertRepository, Depends(get_alert_repo)],
) -> dict[str, object]:
    alert = await alerts.get(alert_id)

    if alert is None:
        raise HTTPException(404, detail="Alert not found")

    return {
        "id": str(alert.id),
        "device_id": str(alert.device_id),
        "severity": alert.severity,
        "condition": alert.condition,
        "state": alert.state,
        "created_at": alert.created_at.isoformat(),
    }


@router.post("/alerts", status_code=201)
async def create_alert(
    body: AlertCreate,
    alerts: Annotated[AlertRepository, Depends(get_alert_repo)],
) -> dict[str, object]:
    alert = await alerts.create(
        device_id=body.device_id,
        severity=body.severity,
        condition=body.condition,
        state=body.state,
    )

    return {
        "id": str(alert.id),
        "device_id": str(alert.device_id),
        "severity": alert.severity,
        "condition": alert.condition,
        "state": alert.state,
    }