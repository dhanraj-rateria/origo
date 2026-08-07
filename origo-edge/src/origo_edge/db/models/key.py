from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ...domain.enums import KemParamSet, KeyState
from ..base import Base, Timestamps, UUIDPrimaryKey


class Key(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "keys"

    satellite_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    ground_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    kem_param_set: Mapped[KemParamSet] = mapped_column(Enum(KemParamSet, native_enum=False, length=32), nullable=False)
    state: Mapped[KeyState] = mapped_column(
        Enum(KeyState, native_enum=False, length=32), default=KeyState.PENDING_KEYGEN, nullable=False, index=True
    )
    hsm_key_reference: Mapped[str | None] = mapped_column(String(128))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("keys.id", ondelete="SET NULL"))

    __table_args__ = (
        # At most one ACTIVE key per device pair — enforced by the database so a race
        # under concurrent activation can't produce two, not just checked in Python.
        Index(
            "uq_keys_one_active_per_pair", "satellite_device_id", "ground_device_id",
            unique=True, postgresql_where=(state == KeyState.ACTIVE),
        ),
    )