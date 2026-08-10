"""Turns OrigoSpaceAgent into something that can run as its own container and be
reached over a network — which a real satellite never is (§2: "no live channel...
in either direction"), but a *software stand-in* for one has to be, if the Docker
device loop is going to exercise a real handshake across a real container boundary
instead of two Python objects in the same test process.

This is the mocked half of "RF and StellarStation are a mock for now": everything
below the HTTP layer (WolfCryptEngine, IdentityStore, OrigoSpaceAgent, the envelope
wire format) is the real, unmodified crypto path. The only thing invented here is
*how a pass gets triggered* — a real satellite acts autonomously when a pass
condition is met during a real contact; this stands in for that with a plain HTTP
call, made by origo_info_adapter.dockerlink.DockerLink on origo-station-agent's
behalf.

Endpoints:
  GET  /health          liveness probe (docker HEALTHCHECK, and the provisioner's
                         wait-until-ready poll)
  GET  /identity         this device's own public key — provisioning-time only
  POST /peer              store the paired Origo Terrestrial's public key — the
                         provisioner calls this once, after both containers exist
  POST /downlink/trigger  §5.2 steps 3-4: KeyGen + sign ek, "transmit" it
  POST /uplink             §5.2 step 7: verify + Decapsulate the returned ct
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from origo_crypto.wolfcrypt_engine import WolfCryptEngine

from .agent import OrigoSpaceAgent
from .identity import IdentityStore

DEVICE_ID = os.environ.get("ORIGO_SPACE_DEVICE_ID", "aster-1")
IDENTITY_PATH = Path(os.environ.get("ORIGO_SPACE_IDENTITY_PATH", "identity.json"))

app = FastAPI(title="Origo Space (software stand-in)")

_engine = WolfCryptEngine()
_identity = IdentityStore(path=IDENTITY_PATH, engine=_engine)
_agent = OrigoSpaceAgent(engine=_engine, identity=_identity, device_id=DEVICE_ID)
_peer_public_key: bytes | None = None   # Origo Terrestrial's ML-DSA public key


class PeerKey(BaseModel):
    public_key_hex: str


class UplinkEnvelope(BaseModel):
    envelope_hex: str


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "device_id": DEVICE_ID}


@app.get("/identity")
def identity() -> dict[str, str]:
    return {"device_id": DEVICE_ID, "public_key_hex": _identity.public_key.hex()}


@app.post("/peer")
def set_peer(body: PeerKey) -> dict[str, str]:
    global _peer_public_key
    try:
        _peer_public_key = bytes.fromhex(body.public_key_hex)
    except ValueError as exc:
        raise HTTPException(400, "public_key_hex is not valid hex") from exc
    return {"status": "ok"}


@app.post("/downlink/trigger")
def trigger_downlink() -> dict[str, str]:
    """What a real RF chain would transmit during a pass — see design §5.2 step 4."""
    envelope = _agent.initiate_key_exchange()
    return {"device_id": DEVICE_ID, "envelope_hex": envelope.hex()}


@app.post("/uplink")
def receive_uplink(body: UplinkEnvelope) -> dict[str, object]:
    """What a real RF chain would have received during a pass — design §5.2 step 7."""
    if _peer_public_key is None:
        raise HTTPException(409, "no peer public key set — call POST /peer first")
    try:
        envelope = bytes.fromhex(body.envelope_hex)
    except ValueError as exc:
        raise HTTPException(400, "envelope_hex is not valid hex") from exc
    try:
        traffic_key = _agent.process_ct_envelope(envelope, peer_public_key=_peer_public_key)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    # The traffic key itself never leaves this process (KemKeypair.dk's own docstring
    # rule, applied here too) — a short fingerprint is enough to confirm both sides
    # derived the same key without putting the key on the wire a second time.
    fingerprint = hashlib.sha256(traffic_key).hexdigest()[:16]
    return {"status": "ok", "key_fingerprint": fingerprint}
