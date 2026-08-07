# origo-station-agent/tests/fake_origo.py
from __future__ import annotations

from origo_station_agent.origo.ports import EncapsulationResult, OrigoTerrestrialStatus


class FakeOrigoTerrestrial:
    """Same awkward semantics as the real thing: rejects on demand, doesn't silently
    succeed. Not a kinder fake."""

    def __init__(self) -> None:
        self.encapsulate_calls: list[dict] = []
        self.decrypt_calls: list[dict] = []
        self.reject_encapsulate = False
        self.reject_decrypt_after: int | None = None

    async def health(self) -> OrigoTerrestrialStatus:
        return OrigoTerrestrialStatus(
            tamper_clear=True, entropy_healthy=True, self_test_passed=True,
            active_key_id="key-1", error_count=0, temperature_c=24.0,
        )

    async def verify_and_encapsulate(self, *, ek, signature, device_id, nonce) -> EncapsulationResult:
        from origo_station_agent.errors import OrigoRejected
        self.encapsulate_calls.append({"ek": ek, "device_id": device_id})
        if self.reject_encapsulate:
            raise OrigoRejected("bad signature")
        return EncapsulationResult(ciphertext=b"ct-bytes", signature=b"ct-sig", key_id="key-42")

    async def decrypt_payload(self, *, key_id, ciphertext, sequence_number) -> bytes:
        from origo_station_agent.errors import OrigoRejected
        self.decrypt_calls.append({"key_id": key_id, "seq": sequence_number})
        if self.reject_decrypt_after is not None and sequence_number >= self.reject_decrypt_after:
            raise OrigoRejected(f"replay or bad ciphertext at seq {sequence_number}")
        return b"plaintext-" + ciphertext

    async def apply_config(self, *, signed_config) -> None:
        pass