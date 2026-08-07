from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from ...domain.enums import DeviceStatus, DeviceType
from ..base import Base, Timestamps, UUIDPrimaryKey


class Device(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "devices"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[DeviceType] = mapped_column(Enum(DeviceType, native_enum=False, length=32), nullable=False, index=True)
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, native_enum=False, length=32), default=DeviceStatus.PROVISIONED, nullable=False, index=True
    )
    mission: Mapped[str | None] = mapped_column(String(128))
    serial_number: Mapped[str | None] = mapped_column(String(128))
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))