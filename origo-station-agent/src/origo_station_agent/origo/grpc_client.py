"""gRPC implementation of OrigoTerrestrial. Same-hardware link (Unix domain socket) —
see settings.py and main.py."""

from __future__ import annotations

import grpc
import structlog

from .._proto.origo.v1 import origo_pb2 as pb
from .._proto.origo.v1 import origo_pb2_grpc as pb_grpc
from ..errors import OrigoRejected, OrigoUnavailable
from .ports import EncapsulationResult, OrigoTerrestrialStatus

log = structlog.get_logger(__name__)


class GrpcOrigoTerrestrial:
    def __init__(self, *, channel: grpc.aio.Channel, timeout_sec: float = 10.0) -> None:
        # OrigoTerrestrialServiceStub — the name protoc actually generates from
        # `service OrigoTerrestrialService` in origo.proto.
        self._stub = pb_grpc.OrigoTerrestrialServiceStub(channel)
        self._timeout = timeout_sec

    async def health(self) -> OrigoTerrestrialStatus:
        try:
            resp = await self._stub.Health(pb.HealthRequest(), timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            raise OrigoUnavailable(f"health check failed: {exc.details()}", cause=exc) from exc
        return OrigoTerrestrialStatus(
            tamper_clear=resp.tamper_clear, entropy_healthy=resp.entropy_healthy,
            self_test_passed=resp.self_test_passed,
            active_key_id=resp.active_key_id or None,
            error_count=resp.error_count, temperature_c=resp.temperature_c or None,
        )

    async def verify_and_encapsulate(
        self, *, ek: bytes, signature: bytes, device_id: str, nonce: bytes,
    ) -> EncapsulationResult:
        req = pb.VerifyAndEncapsulateRequest(ek=ek, signature=signature, device_id=device_id, nonce=nonce)
        try:
            resp = await self._stub.VerifyAndEncapsulate(req, timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            if exc.code() is grpc.StatusCode.INVALID_ARGUMENT:
                raise OrigoRejected(f"Origo Terrestrial rejected ek: {exc.details()}", cause=exc) from exc
            raise OrigoUnavailable(f"verify_and_encapsulate failed: {exc.details()}", cause=exc) from exc
        log.info("origo.encapsulated", device_id=device_id, key_id=resp.key_id)
        return EncapsulationResult(ciphertext=resp.ciphertext, signature=resp.signature, key_id=resp.key_id)

    async def decrypt_payload(self, *, key_id: str, ciphertext: bytes, sequence_number: int) -> bytes:
        req = pb.DecryptPayloadRequest(key_id=key_id, ciphertext=ciphertext, sequence_number=sequence_number)
        try:
            resp = await self._stub.DecryptPayload(req, timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            if exc.code() is grpc.StatusCode.INVALID_ARGUMENT:
                raise OrigoRejected(f"Origo Terrestrial rejected ciphertext: {exc.details()}", cause=exc) from exc
            raise OrigoUnavailable(f"decrypt_payload failed: {exc.details()}", cause=exc) from exc
        return resp.plaintext

    async def apply_config(self, *, signed_config: bytes) -> None:
        try:
            await self._stub.ApplyConfig(pb.ApplyConfigRequest(signed_config=signed_config), timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            raise OrigoUnavailable(f"apply_config failed: {exc.details()}", cause=exc) from exc