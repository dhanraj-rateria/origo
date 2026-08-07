# services/key_service.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..clock import utcnow
from ..db.models.key import Key
from ..domain.enums import DeviceType, DeviceStatus, KemParamSet, KeyState
from ..domain.errors import NotFound, PolicyViolation
from ..domain.key_lifecycle import KEY_MACHINE
from ..repositories.device import DeviceRepository
from ..repositories.key import KeyRepository


class KeyService:
    def __init__(self, *, session: AsyncSession, keys: KeyRepository, devices: DeviceRepository) -> None:
        self._session, self._keys, self._devices = session, keys, devices

    async def create_pending(
        self, *, satellite_device_id: uuid.UUID, ground_device_id: uuid.UUID, kem_param_set: KemParamSet,
    ) -> Key:
        sat = await self._devices.get(satellite_device_id)
        gnd = await self._devices.get(ground_device_id)
        if sat is None:
            raise NotFound("device", satellite_device_id)
        if gnd is None:
            raise NotFound("device", ground_device_id)
        if sat.type is not DeviceType.ORIGO_SPACE:
            raise PolicyViolation(f"device {sat.id} is {sat.type}, expected {DeviceType.ORIGO_SPACE}")
        if gnd.type is not DeviceType.ORIGO_TERRESTRIAL:
            raise PolicyViolation(f"device {gnd.id} is {gnd.type}, expected {DeviceType.ORIGO_TERRESTRIAL}")
        if sat.status is not DeviceStatus.ACTIVE or gnd.status is not DeviceStatus.ACTIVE:
            raise PolicyViolation("both devices must be ACTIVE to establish a key")

        return await self._keys.create(
            satellite_device_id=satellite_device_id, ground_device_id=ground_device_id,
            kem_param_set=kem_param_set, state=KeyState.PENDING_KEYGEN,
        )

    async def advance(self, *, key_id: uuid.UUID, target: KeyState, hsm_key_reference: str | None = None) -> Key:
        key = await self._keys.get_for_update(key_id)
        if key is None:
            raise NotFound("key", key_id)

        previous = key.state
        key.state = KEY_MACHINE.transition(current=previous, target=target)

        now = utcnow()
        if target is KeyState.ACTIVE:
            key.activated_at = now
            if hsm_key_reference:
                key.hsm_key_reference = hsm_key_reference
            for old in await self._keys.list_active_for_pair(
                satellite_device_id=key.satellite_device_id, ground_device_id=key.ground_device_id, exclude_id=key.id,
            ):
                old.state = KEY_MACHINE.transition(current=old.state, target=KeyState.SUPERSEDED)
                old.superseded_by_key_id = key.id
                old.retired_at = now
        elif target in {KeyState.SUPERSEDED, KeyState.REVOKED, KeyState.DESTROYED}:
            key.retired_at = now

        return key