from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.telemetry_record import TelemetryRecord


class TelemetryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        telemetry_id: uuid.UUID,
    ) -> TelemetryRecord | None:
        return await self._session.get(TelemetryRecord, telemetry_id)

    async def list(
        self,
        *,
        source_device_id: uuid.UUID | None = None,
        metric_type: str | None = None,
    ) -> list[TelemetryRecord]:
        stmt = select(TelemetryRecord).order_by(
            TelemetryRecord.recorded_at.desc()
        )

        if source_device_id is not None:
            stmt = stmt.where(
                TelemetryRecord.source_device_id == source_device_id
            )

        if metric_type is not None:
            stmt = stmt.where(
                TelemetryRecord.metric_type == metric_type
            )

        return list((await self._session.execute(stmt)).scalars())

    async def create(self, **fields: object) -> TelemetryRecord:
        record = TelemetryRecord(**fields)
        self._session.add(record)
        await self._session.flush()
        return record