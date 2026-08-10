# origo-crypto/src/origo_crypto/envelope.py
"""Same wire format as origo_station_agent.pass_executor's _parse_kem_envelope /
_frame_ct — this is a shared contract, not a coincidence. If either side changes, both
must change together; that's the honest reason this isn't defined once and imported —
Origo Space software shouldn't depend on origo-station-agent's package, so the format
is specified independently in both places with this comment as the cross-reference.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

_MAGIC = b"OSKX"


def _pack(*parts: bytes) -> bytes:
    out = bytearray()
    for p in parts:
        out += struct.pack(">I", len(p)) + p
    return bytes(out)


def _unpack(data: bytes, count: int) -> list[bytes] | None:
    out, offset = [], 0
    for _ in range(count):
        if offset + 4 > len(data):
            return None
        (length,) = struct.unpack(">I", data[offset:offset + 4])
        offset += 4
        if offset + length > len(data):
            return None
        out.append(data[offset:offset + length])
        offset += length
    return out


@dataclass(frozen=True, slots=True)
class KemEnvelope:
    ek: bytes
    signature: bytes
    device_id: str
    nonce: bytes


def pack_ek_envelope(*, ek: bytes, signature: bytes, device_id: str, nonce: bytes) -> bytes:
    return _MAGIC + _pack(ek, signature, device_id.encode(), nonce)


def parse_ek_envelope(data: bytes) -> KemEnvelope | None:
    if not data.startswith(_MAGIC):
        return None
    fields = _unpack(data[len(_MAGIC):], 4)
    if fields is None:
        return None
    ek, sig, device_id, nonce = fields
    return KemEnvelope(ek=ek, signature=sig, device_id=device_id.decode(), nonce=nonce)


def pack_ct_envelope(*, ciphertext: bytes, signature: bytes) -> bytes:
    return _MAGIC + _pack(ciphertext, signature)


def parse_ct_envelope(data: bytes) -> tuple[bytes, bytes] | None:
    if not data.startswith(_MAGIC):
        return None
    fields = _unpack(data[len(_MAGIC):], 2)
    return (fields[0], fields[1]) if fields else None