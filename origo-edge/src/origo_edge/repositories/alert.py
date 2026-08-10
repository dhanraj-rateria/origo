from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.alert import Alert


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, alert_id: uuid.UUID) -> Alert | None:
        return await self._session.get(Alert, alert_id)

    async def list(
        self,
        *,
        device_id: uuid.UUID | None = None,
        severity: str | None = None,
        state: str | None = None,
    ) -> list[Alert]:
        stmt = select(Alert).order_by(Alert.created_at.desc())

        if device_id is not None:
            stmt = stmt.where(Alert.device_id == device_id)

        if severity is not None:
            stmt = stmt.where(Alert.severity == severity)

        if state is not None:
            stmt = stmt.where(Alert.state == state)

        return list((await self._session.execute(stmt)).scalars())

    async def create(self, **fields: object) -> Alert:
        alert = Alert(**fields)
        self._session.add(alert)
        await self._session.flush()
        return alert