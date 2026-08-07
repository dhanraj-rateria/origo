# repositories/key.py
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.key import Key
from ..domain.enums import KeyState


class KeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(self, key_id: uuid.UUID) -> Key | None:
        stmt = select(Key).where(Key.id == key_id).with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list(self) -> list[Key]:
        stmt = select(Key).order_by(Key.created_at.desc())
        return list((await self._session.execute(stmt)).scalars())

    async def list_active_for_pair(
        self, *, satellite_device_id: uuid.UUID, ground_device_id: uuid.UUID, exclude_id: uuid.UUID | None = None,
    ) -> list[Key]:
        stmt = select(Key).where(
            Key.satellite_device_id == satellite_device_id,
            Key.ground_device_id == ground_device_id,
            Key.state == KeyState.ACTIVE,
        )
        if exclude_id is not None:
            stmt = stmt.where(Key.id != exclude_id)
        return list((await self._session.execute(stmt)).scalars())

    async def create(self, **fields: object) -> Key:
        key = Key(**fields)
        self._session.add(key)
        await self._session.flush()
        return key