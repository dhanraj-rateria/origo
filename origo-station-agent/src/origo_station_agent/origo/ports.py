"""The local link to the Origo Terrestrial (Origo Terrestrial Interface Driver).

Nothing crosses this boundary except signed/encrypted bytes in, signed/encrypted bytes
or plaintext-for-local-forwarding out. This process never sees a private key, a session key,
or unwrapped key material — that discipline is enforced by Origo Terrestrial refusing to hand it over.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class OrigoTerrestrialStatus:
    __slots__ = (
        "tamper_clear", "entropy_healthy", "self_test_passed",
        "active_key_id", "error_count", "temperature_c",
    )

    def __init__(
        self, *, tamper_clear: bool, entropy_healthy: bool, self_test_passed: bool,
        active_key_id: str | None, error_count: int, temperature_c: float | None,
    ) -> None:
        self.tamper_clear = tamper_clear
        self.entropy_healthy = entropy_healthy
        self.self_test_passed = self_test_passed
        self.active_key_id = active_key_id
        self.error_count = error_count
        self.temperature_c = temperature_c


class EncapsulationResult:
    __slots__ = ("ciphertext", "signature", "key_id")

    def __init__(self, *, ciphertext: bytes, signature: bytes, key_id: str) -> None:
        self.ciphertext = ciphertext
        self.signature = signature
        self.key_id = key_id


@runtime_checkable
class OrigoTerrestrial(Protocol):
    """One instance per Origo Terrestrial. The Pass Executor
    is the only caller — nothing else in this process should import this module."""

    async def health(self) -> OrigoTerrestrialStatus:
        """Cheap local status pull. Also the source for what sync_client uploads as
        telemetry — this process keeps no health model of its own."""

    async def verify_and_encapsulate(
        self, *, ek: bytes, signature: bytes, device_id: str, nonce: bytes,
    ) -> EncapsulationResult:
        """Raises OrigoRejected on a signature/nonce failure — a security event, not a
        transient fault. The caller must not retry the same bytes."""

    async def decrypt_payload(
        self, *, key_id: str, ciphertext: bytes, sequence_number: int,
    ) -> bytes:
        """A sequence gap or repeat is OrigoRejected, not silently accepted."""

    async def apply_config(self, *, signed_config: bytes) -> None: ...