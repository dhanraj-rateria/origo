from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.pass_ import Pass


class PassRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, pass_id: uuid.UUID) -> Pass | None:
        return await self._session.get(Pass, pass_id)

    async def list(
        self,
        *,
        satellite_device_id: uuid.UUID | None = None,
        ground_device_id: uuid.UUID | None = None,
    ) -> list[Pass]:
        stmt = select(Pass).order_by(Pass.aos.asc())

        if satellite_device_id is not None:
            stmt = stmt.where(Pass.satellite_device_id == satellite_device_id)

        if ground_device_id is not None:
            stmt = stmt.where(Pass.ground_device_id == ground_device_id)

        return list((await self._session.execute(stmt)).scalars())

    async def create(self, **fields: object) -> Pass:
        device_pass = Pass(**fields)
        self._session.add(device_pass)
        await self._session.flush()
        return device_pass