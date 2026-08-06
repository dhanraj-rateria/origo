"""JobPlan / JobPlanStep, the wire contract between origo-edge's
jobplan_service and this agent's sync_client.

Duplicated from origo-edge's own JobPlan shape rather than shared from a common
package — worth promoting to a small `origo-contracts` package the moment the two
definitions actually drift, but a shared package two producers must agree on is a
bigger cost than a duplicated model, until duplication has actually caused a bug.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class JobType(StrEnum):
    KEY_EXCHANGE = "KEY_EXCHANGE"
    DATA_DELIVERY = "DATA_DELIVERY"
    CONFIG_PUSH = "CONFIG_PUSH"
    SELF_TEST = "SELF_TEST"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class JobPlanStep(_Frozen):
    step_id: UUID
    job_id: UUID
    job_type: JobType
    expected_start_offset_sec: int
    timeout_sec: int
    parameters: dict[str, object] = {}


class JobPlan(_Frozen):
    """Signed by origo-edge's KMS-backed key (design §8.3). Verified before any step
    executes — an agent that trusted an unsigned plan would let a compromised network
    path, not even the Platform itself, direct antenna time and Origo Terrestrial operations."""

    plan_id: UUID
    ground_station_id: str
    pass_id: UUID
    valid_from: datetime
    valid_until: datetime
    steps: tuple[JobPlanStep, ...]
    signature: bytes
    signed_payload: bytes

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        return self

    def is_stale(self, *, at: datetime) -> bool:
        """§3.3.2: outside this window, don't execute — treat as stale."""
        return at < self.valid_from or at > self.valid_until