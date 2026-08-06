"""The Pass Executor and the state machine, as code.

Live during a contact window; sequences Origo Terrestrial and the origo_info_adapter
ContactLink against a cached JobPlan. No cloud dependency in this path — everything
needed was pulled by the Sync Client before AOS.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import StrEnum, auto
from uuid import UUID, uuid4

import structlog
from origo_info_adapter import ChannelSetRef, ContactId, GroundNetworkAdapter, SatelliteRef

from .errors import OrigoRejected, OrigoUnavailable, JobPlanStale
from .origo.ports import OrigoTerrestrial
from .models import JobPlan, JobPlanStep, JobType

log = structlog.get_logger(__name__)


class ExecState(StrEnum):
    IDLE = auto()
    AOS_DETECTED = auto()
    EXECUTING_JOBS = auto()
    LOS_DETECTED = auto()
    JOB_TIMEOUT = auto()
    SYNCING = auto()


class StepResult:
    __slots__ = ("step_id", "job_id", "outcome", "detail")

    def __init__(self, *, step_id: UUID, job_id: UUID, outcome: str, detail: dict[str, object]) -> None:
        self.step_id = step_id
        self.job_id = job_id
        self.outcome = outcome     # "ACTIVE" | "FAILED" | "TIMED_OUT" — mirrors origo-edge's JobState
        self.detail = detail


class PassExecutor:
    def __init__(
        self, *, adapter: GroundNetworkAdapter, origo: OrigoTerrestrial,
        satellite_ref: SatelliteRef, station_ref: str,
    ) -> None:
        self._adapter = adapter
        self._origo = origo
        self._satellite_ref = satellite_ref
        self._station_ref = station_ref
        self.state = ExecState.IDLE
        self.results: list[StepResult] = []

    async def run(
        self, *, plan: JobPlan, contact_id: ContactId, now: datetime,
    ) -> list[StepResult]:
        """One call per pass. Returns when every step resolves or LOS closes the link."""
        if plan.is_stale(at=now):
            raise JobPlanStale(f"plan {plan.plan_id} outside its validity window")

        self.state = ExecState.AOS_DETECTED
        self.results = []
        log.info("pass.aos", pass_id=str(plan.pass_id), steps=len(plan.steps))

        self.state = ExecState.EXECUTING_JOBS
        async with self._adapter.open_link(
            satellite_ref=self._satellite_ref, contact_id=contact_id,
            station_ref=self._station_ref,
        ) as link:
            for step in plan.steps:
                try:
                    result = await asyncio.wait_for(
                        self._run_step(step, link), timeout=step.timeout_sec,
                    )
                except TimeoutError:
                    log.warning("step.timeout", step_id=str(step.step_id))
                    result = StepResult(
                        step_id=step.step_id, job_id=step.job_id, outcome="TIMED_OUT",
                        detail={"reason": f"no result within {step.timeout_sec}s"},
                    )
                    self.state = ExecState.JOB_TIMEOUT
                self.results.append(result)

        self.state = ExecState.LOS_DETECTED
        log.info(
            "pass.los", pass_id=str(plan.pass_id),
            outcomes={str(r.job_id): r.outcome for r in self.results},
        )
        self.state = ExecState.SYNCING
        return self.results

    async def _run_step(self, step: JobPlanStep, link) -> StepResult:
        if step.job_type is JobType.KEY_EXCHANGE:
            return await self._run_key_exchange(step, link)
        if step.job_type is JobType.DATA_DELIVERY:
            return await self._run_data_delivery(step, link)
        if step.job_type is JobType.CONFIG_PUSH:
            return await self._run_config_push(step)
        raise ValueError(f"unhandled job_type: {step.job_type}")

    async def _run_key_exchange(self, step: JobPlanStep, link) -> StepResult:
        """Ground side: wait for the signed `ek` on the downlink, 
        hand it to the Origo Terrestrial, uplink the resulting signed `ct`."""
        async for frame in link.frames():
            envelope = _parse_kem_envelope(frame.data)
            if envelope is None:
                continue    # not a key-exchange frame — some other traffic on this link
            try:
                result = await self._origo.verify_and_encapsulate(
                    ek=envelope.ek, signature=envelope.signature,
                    device_id=envelope.device_id, nonce=envelope.nonce,
                )
            except OrigoRejected as exc:
                log.warning("kex.origo_rejected", job_id=str(step.job_id), error=str(exc))
                return StepResult(
                    step_id=step.step_id, job_id=step.job_id, outcome="FAILED",
                    detail={"reason": str(exc)},
                )
            except OrigoUnavailable as exc:
                return StepResult(
                    step_id=step.step_id, job_id=step.job_id, outcome="FAILED",
                    detail={"reason": f"Origo unavailable: {exc}"},
                )

            ack = await link.send_commands(
                _frame_ct(result.ciphertext, result.signature),
                channel_set_ref=ChannelSetRef(str(step.parameters.get("channel_set_ref", ""))),
                request_id=str(uuid4()),
            )
            log.info(
                "kex.ct_uplinked", job_id=str(step.job_id), key_id=result.key_id,
                request_id=ack.request_id,
            )
            return StepResult(
                step_id=step.step_id, job_id=step.job_id, outcome="ACTIVE",
                detail={"key_id": result.key_id},
            )

        return StepResult(
            step_id=step.step_id, job_id=step.job_id, outcome="TIMED_OUT",
            detail={"reason": "link closed before ek arrived"},
        )

    async def _run_data_delivery(self, step: JobPlanStep, link) -> StepResult:
        """Decrypt downlinked ciphertext under the active session key.
        `detail['plaintext']` is what main.py's sync loop queues for upload — this is
        the mechanism behind 'the data is received and the user can view it on the
        platform,' from the very first version of this design."""
        key_id = str(step.parameters.get("key_id", ""))
        seq = 0
        chunks: list[bytes] = []
        async for frame in link.frames():
            try:
                plaintext = await self._origo.decrypt_payload(
                    key_id=key_id, ciphertext=frame.data, sequence_number=seq,
                )
            except OrigoRejected as exc:
                log.warning("delivery.origo_rejected", job_id=str(step.job_id), seq=seq, error=str(exc))
                return StepResult(
                    step_id=step.step_id, job_id=step.job_id, outcome="FAILED",
                    detail={"reason": str(exc), "bytes_before_failure": sum(len(c) for c in chunks)},
                )
            chunks.append(plaintext)
            seq += 1
        return StepResult(
            step_id=step.step_id, job_id=step.job_id, outcome="ACTIVE",
            detail={"plaintext": b"".join(chunks), "frame_count": seq},
        )

    async def _run_config_push(self, step: JobPlanStep) -> StepResult:
        blob = step.parameters.get("signed_config")
        if not isinstance(blob, (bytes, bytearray)):
            return StepResult(
                step_id=step.step_id, job_id=step.job_id, outcome="FAILED",
                detail={"reason": "missing signed_config"},
            )
        try:
            await self._origo.apply_config(signed_config=bytes(blob))
        except OrigoUnavailable as exc:
            return StepResult(
                step_id=step.step_id, job_id=step.job_id, outcome="FAILED",
                detail={"reason": str(exc)},
            )
        return StepResult(step_id=step.step_id, job_id=step.job_id, outcome="ACTIVE", detail={})


class _KemEnvelope:
    __slots__ = ("ek", "signature", "device_id", "nonce")

    def __init__(self, *, ek: bytes, signature: bytes, device_id: str, nonce: bytes) -> None:
        self.ek, self.signature, self.device_id, self.nonce = ek, signature, device_id, nonce


def _parse_kem_envelope(data: bytes) -> _KemEnvelope | None:
    """Deserialise the framing carrying ek+signature+device_id+nonce off the downlink.
    This byte-level envelope format isn't specified anywhere yet — pick
    a small TLV or length-prefixed layout and put it here and in the Module firmware's
    encoder as each other's only spec. Returns None for a frame that isn't this format,
    so unrelated traffic on the same link is ignored rather than raising."""
    raise NotImplementedError


def _frame_ct(ciphertext: bytes, signature: bytes) -> list[bytes]:
    """Inverse of the above for the uplink direction (§5.2 step 6). ml-kem-1024's ct
    (1568 B) plus an ML-DSA-87 signature (several KB) may need splitting across more
    than one command in the burst — send_commands() already accepts a sequence for
    exactly this."""
    raise NotImplementedError