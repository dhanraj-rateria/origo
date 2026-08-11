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
    # Which device (by serial_number) this one exchanges keys with. Optional and only
    # meaningful today for the Docker device-loop provisioner — not a general
    # fleet-topology model.
    peer_serial_number: Mapped[str | None] = mapped_column(String(128))
    # Outcome of the Docker device-loop provisioner's last attempt for this device:
    # "running" / "provisioning_failed" / "not_provisioned", or NULL if provisioning
    # was never attempted (real devices, or ORIGO_DEVICE_PROVISIONING_ENABLED=false).
    # Deliberately named around "provisioning," not "container" — a real device
    # simply never gets this field populated rather than needing it repurposed once
    # real hardware exists. Not a substitute for real connectivity/health telemetry,
    # which doesn't exist yet (see origo-edge's "known gaps": Telemetry is still a
    # fixture).
    provisioning_status: Mapped[str | None] = mapped_column(String(32))
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))