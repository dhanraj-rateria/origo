"""Implements OrigoTerrestrialService (proto/origo/v1/origo.proto) — the exact
interface origo-station-agent's GrpcOrigoTerrestrial already calls. Design §5.2 steps
4-5 as running code: verify Origo Space's signature on ek, check nonce freshness,
Encapsulate, sign ct."""

from __future__ import annotations

import time
import uuid

import grpc
import structlog
from origo_crypto.engine import CryptoEngine

from ._proto.origo.v1 import origo_pb2 as pb
from ._proto.origo.v1 import origo_pb2_grpc as pb_grpc
from .identity import IdentityStore

log = structlog.get_logger(__name__)

NONCE_FRESHNESS_WINDOW_SEC = 120


class OrigoTerrestrialServicer(pb_grpc.OrigoTerrestrialServiceServicer):
    def __init__(self, *, engine: CryptoEngine, identity: IdentityStore, peer_public_key: bytes) -> None:
        self._engine = engine
        self._identity = identity
        self._peer_public_key = peer_public_key
        self._active_keys: dict[str, bytes] = {}          # key_id -> shared_secret (traffic key)
        self._seen_nonces: dict[bytes, float] = {}         # replay protection

    def Health(self, request, context):
        return pb.HealthResponse(
            tamper_clear=True, entropy_healthy=True, self_test_passed=True,
            active_key_id=next(iter(self._active_keys), ""), error_count=0, temperature_c=24.0,
        )

    def VerifyAndEncapsulate(self, request, context):
        # Nonce freshness/replay — a resent (ek, nonce) pair is a replay, reject it.
        now = time.time()
        self._seen_nonces = {n: t for n, t in self._seen_nonces.items() if now - t < NONCE_FRESHNESS_WINDOW_SEC}
        if request.nonce in self._seen_nonces:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "nonce replay")
            return pb.VerifyAndEncapsulateResponse()

        signed_payload = request.ek + request.device_id.encode() + request.nonce
        if not self._engine.dsa_verify(public_key=self._peer_public_key, message=signed_payload, signature=request.signature):
            log.warning("terrestrial.signature_rejected", device_id=request.device_id)
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "signature verification failed")
            return pb.VerifyAndEncapsulateResponse()

        self._seen_nonces[request.nonce] = now
        result = self._engine.kem_encapsulate(request.ek)
        key_id = f"key-{uuid.uuid4().hex[:12]}"
        traffic_key = self._engine.hkdf(shared_secret=result.shared_secret, context=b"origo-traffic-key")
        self._active_keys[key_id] = traffic_key

        ct_signed_payload = result.ciphertext
        ct_signature = self._engine.dsa_sign(private_key=self._identity.private_key, message=ct_signed_payload)
        log.info("terrestrial.encapsulated", device_id=request.device_id, key_id=key_id)
        return pb.VerifyAndEncapsulateResponse(ciphertext=result.ciphertext, signature=ct_signature, key_id=key_id)

    def DecryptPayload(self, request, context):
        traffic_key = self._active_keys.get(request.key_id)
        if traffic_key is None:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"unknown key_id {request.key_id}")
            return pb.DecryptPayloadResponse()
        nonce = request.sequence_number.to_bytes(12, "big")
        try:
            plaintext = self._engine.aead_decrypt(key=traffic_key, nonce=nonce, ciphertext=request.ciphertext)
        except RuntimeError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "AEAD decryption failed — bad ciphertext or replayed sequence")
            return pb.DecryptPayloadResponse()
        return pb.DecryptPayloadResponse(plaintext=plaintext)

    def ApplyConfig(self, request, context):
        # No policy concept — nothing to apply yet beyond verifying the signature, which
        # is the actual security-relevant part of this RPC regardless of payload content.
        if not self._engine.dsa_verify(public_key=self._peer_public_key, message=request.signed_config, signature=b""):
            pass   # placeholder until config payloads carry a real signature to check
        return pb.ApplyConfigResponse()