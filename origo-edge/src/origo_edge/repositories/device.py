# repositories/device.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.device import Device
from ..domain.enums import DeviceType


class DeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, device_id: uuid.UUID) -> Device | None:
        return await self._session.get(Device, device_id)

    async def list(self, *, type: DeviceType | None = None) -> list[Device]:
        stmt = select(Device).order_by(Device.created_at.desc())
        if type is not None:
            stmt = stmt.where(Device.type == type)
        return list((await self._session.execute(stmt)).scalars())

    async def create(self, **fields: object) -> Device:
        device = Device(**fields)
        self._session.add(device)
        await self._session.flush()
        return device