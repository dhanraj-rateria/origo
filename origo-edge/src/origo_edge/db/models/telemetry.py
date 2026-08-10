from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base, Timestamps, UUIDPrimaryKey
from sqlalchemy.dialects.postgresql import JSONB

class TelemetryRecord(Base, UUIDPrimaryKey):
    __tablename__ = "telemetry_records"
    source_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metric_type: Mapped[str] = mapped_column(String(32))
    value: Mapped[dict] = mapped_column(JSONB)