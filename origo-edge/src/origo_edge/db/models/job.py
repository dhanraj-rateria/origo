from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ...domain.enums import JobState, JobType
from ..base import Base, Timestamps, UUIDPrimaryKey


class Job(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "jobs"

    type: Mapped[JobType] = mapped_column(Enum(JobType, native_enum=False, length=32), nullable=False, index=True)
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, native_enum=False, length=32), default=JobState.SCHEDULED, nullable=False, index=True
    )
    satellite_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False, index=True)
    ground_device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False, index=True)
    key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("keys.id", ondelete="SET NULL"))
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False, server_default="{}")
    failure_reason: Mapped[str | None] = mapped_column(String(512))