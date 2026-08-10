"""The crypto contract both Origo Space and Origo Terrestrial drive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class KemKeypair:
    ek: bytes
    dk: bytes   # never serialized, never leaves the process that generated it


@dataclass(frozen=True, slots=True)
class EncapsResult:
    ciphertext: bytes
    shared_secret: bytes


class CryptoEngine(Protocol):
    def kem_keygen(self) -> KemKeypair: ...
    def kem_encapsulate(self, ek: bytes) -> EncapsResult: ...
    def kem_decapsulate(self, dk: bytes, ciphertext: bytes) -> bytes: ...
    def dsa_keygen(self) -> tuple[bytes, bytes]: ...              # (public, private)
    def dsa_sign(self, *, private_key: bytes, message: bytes) -> bytes: ...
    def dsa_verify(self, *, public_key: bytes, message: bytes, signature: bytes) -> bool: ...
    def aead_encrypt(self, *, key: bytes, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> bytes: ...
    def aead_decrypt(self, *, key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes: ...
    def hkdf(self, *, shared_secret: bytes, context: bytes, length: int = 32) -> bytes: ...
    def random_bytes(self, n: int) -> bytes: ...