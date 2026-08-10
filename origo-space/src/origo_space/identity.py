# origo-space-sw/src/origo_space_sw/agent.py
"""Software Origo Space. Deliberately simple, per the 'no policy' correction: this
performs one key exchange when called — no standing loop, no condition-watching. The
'when' is someone else's decision (a script invocation for now; a real trigger from
OBC/flight software once this becomes firmware)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from origo_crypto.engine import CryptoEngine, KemKeypair
from origo_crypto.envelope import pack_ek_envelope, parse_ct_envelope

from .identity import IdentityStore


@dataclass
class PendingExchange:
    keypair: KemKeypair
    nonce: bytes


class OrigoSpaceAgent:
    def __init__(self, *, engine: CryptoEngine, identity: IdentityStore, device_id: str = "aster-1") -> None:
        self._engine = engine
        self._identity = identity
        self._device_id = device_id
        self._pending: PendingExchange | None = None

    def initiate_key_exchange(self) -> bytes:
        """Design §5.2 steps 3-4. Returns the envelope bytes ready for the downlink —
        what a real RF chain would transmit, and what InMemoryAdapter's downlink_script
        stands in for during integration testing (see the end-to-end test below)."""
        keypair = self._engine.kem_keygen()
        nonce = self._engine.random_bytes(16)
        self._pending = PendingExchange(keypair=keypair, nonce=nonce)

        signed_payload = keypair.ek + self._device_id.encode() + nonce
        signature = self._engine.dsa_sign(private_key=self._identity.private_key, message=signed_payload)
        return pack_ek_envelope(ek=keypair.ek, signature=signature, device_id=self._device_id, nonce=nonce)

    def process_ct_envelope(self, envelope: bytes, *, peer_public_key: bytes) -> bytes:
        """Design §5.2 step 7. Returns the derived traffic key. Raises if the pending
        exchange doesn't match or the signature is bad — the caller decides what to do
        with that (log, alert, retry on the next contact)."""
        if self._pending is None:
            raise RuntimeError("no key exchange in progress")
        parsed = parse_ct_envelope(envelope)
        if parsed is None:
            raise ValueError("not a valid ct envelope")
        ciphertext, signature = parsed

        if not self._engine.dsa_verify(public_key=peer_public_key, message=ciphertext, signature=signature):
            raise ValueError("ct signature verification failed")

        shared_secret = self._engine.kem_decapsulate(self._pending.keypair.dk, ciphertext)
        traffic_key = self._engine.hkdf(shared_secret=shared_secret, context=b"origo-traffic-key")
        self._pending = None   # zeroize intent — dk and shared_secret go out of scope here;
                                # real firmware should explicitly wipe this memory, which
                                # Python can't guarantee the way C can
        return traffic_key