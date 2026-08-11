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
  GET  /health              liveness probe (docker HEALTHCHECK, and the
                             provisioner's wait-until-ready poll)
  GET  /identity              this device's own public key — provisioning-time only
  POST /peer                    store the paired Origo Terrestrial's public key —
                             the provisioner calls this once, after both containers
                             exist
  POST /downlink/trigger        §5.2 steps 3-4: KeyGen + sign ek, "transmit" it
  POST /uplink                    §5.2 step 7: verify + Decapsulate the returned ct
  POST /downlink/data/stage        queue a plaintext payload for encrypted downlink
                             (DATA_DELIVERY demo)
  POST /downlink/data              hand back the next queued, encrypted chunk
  GET  /downlink/data/status         how many chunks remain — what
                             DockerLink.frames() polls to decide whether this pass is
                             a data-delivery pass or a key-exchange pass; see that
                             file's own docstring for why that's a safe heuristic
                             here and not a general answer to "which job is this"

--- Data chunk wire format (DATA_DELIVERY demo only) --------------------------------
`/downlink/data` returns raw AES-256-GCM ciphertext (encrypted payload + 16-byte tag),
nothing else — no magic bytes, no embedded sequence number. That's not an
oversimplification: origo_station_agent.pass_executor._run_data_delivery tracks its
own sequence number locally (0, 1, 2... in the order frames arrive) and passes it
straight to Origo Terrestrial's DecryptPayload as the nonce source — it never reads a
sequence number out of the frame itself. Embedding one here would just be four extra
bytes DecryptPayload doesn't expect and would fail to authenticate against.

The one thing that constraint pushes onto this file: `_next_seq` MUST reset to 0 at
the start of every new staged batch, since the consumer's own counter resets to 0 for
every fresh DATA_DELIVERY step. `stage_data()` enforces "one batch in flight at a
time" for exactly this reason — see its docstring.
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

DATA_CHUNK_BYTES = 200   # deliberately small — forces multi-frame chunking in the demo

app = FastAPI(title="Origo Space (software stand-in)")

_engine = WolfCryptEngine()
_identity = IdentityStore(path=IDENTITY_PATH, engine=_engine)
_agent = OrigoSpaceAgent(engine=_engine, identity=_identity, device_id=DEVICE_ID)
_peer_public_key: bytes | None = None   # Origo Terrestrial's ML-DSA public key
_traffic_key: bytes | None = None       # set on a successful /uplink; single-key demo scope
_pending_chunks: list[bytes] = []
_next_seq = 0


class PeerKey(BaseModel):
    public_key_hex: str


class UplinkEnvelope(BaseModel):
    envelope_hex: str


class StagePayload(BaseModel):
    plaintext_b64: str


def _nonce_for_seq(seq: int) -> bytes:
    return seq.to_bytes(12, "big")


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
    print(f"[trigger] agent={id(_agent)} pending={id(_agent._pending)} device_id={DEVICE_ID}", flush=True)
    return {"device_id": DEVICE_ID, "envelope_hex": envelope.hex()}


@app.post("/uplink")
def receive_uplink(body: UplinkEnvelope) -> dict[str, object]:
    """What a real RF chain would have received during a pass — design §5.2 step 7."""
    global _traffic_key
    print(f"[uplink] agent={id(_agent)} pending={id(_agent._pending)} peer_key_set={_peer_public_key is not None}", flush=True)
    if _peer_public_key is None:
        raise HTTPException(409, "no peer public key set — call POST /peer first")
    try:
        envelope = bytes.fromhex(body.envelope_hex)
    except ValueError as exc:
        raise HTTPException(400, "envelope_hex is not valid hex") from exc
    print(f"[uplink] calling process_ct_envelope, envelope={len(envelope)} bytes", flush=True)
    try:
        traffic_key = _agent.process_ct_envelope(envelope, peer_public_key=_peer_public_key)
    except (RuntimeError, ValueError) as exc:
        print(f"[uplink] process_ct_envelope raised: {exc!r}", flush=True)
        raise HTTPException(400, str(exc)) from exc
    print("[uplink] process_ct_envelope returned", flush=True)
    _traffic_key = traffic_key   # now available to /downlink/data
    # The traffic key itself never leaves this process (KemKeypair.dk's own docstring
    # rule, applied here too) — a short fingerprint is enough to confirm both sides
    # derived the same key without putting the key on the wire a second time.
    fingerprint = hashlib.sha256(traffic_key).hexdigest()[:16]
    return {"status": "ok", "key_fingerprint": fingerprint}


@app.post("/downlink/data/stage")
def stage_data(body: StagePayload) -> dict[str, object]:
    """Queue a plaintext payload for encrypted downlink. One batch at a time: the
    sequence number Origo Terrestrial's DecryptPayload uses as its nonce source is
    tracked by the *consumer* (pass_executor._run_data_delivery), which resets to 0
    for every fresh DATA_DELIVERY step — so this side's own counter must reset to 0
    for every fresh batch too, or the two sides' sequence numbers (and therefore
    nonces) desync the moment a second batch is staged. Rejecting a stage call while
    a previous batch is still undrained is what keeps that true, rather than silently
    producing ciphertext the second job's decrypt would fail to authenticate."""
    import base64

    global _next_seq
    if _traffic_key is None:
        raise HTTPException(409, "no active traffic key — complete a key exchange first")
    if _pending_chunks:
        raise HTTPException(409, "a previous batch hasn't finished draining yet")
    try:
        plaintext = base64.b64decode(body.plaintext_b64, validate=True)
    except Exception as exc:  # noqa: BLE001 — base64.binascii.Error isn't reliably importable across versions
        raise HTTPException(400, "plaintext_b64 is not valid base64") from exc
    chunks = [plaintext[i : i + DATA_CHUNK_BYTES] for i in range(0, len(plaintext), DATA_CHUNK_BYTES)] or [b""]
    _next_seq = 0
    _pending_chunks.extend(chunks)
    return {"status": "ok", "chunks_queued": len(chunks)}


@app.get("/downlink/data/status")
def data_status() -> dict[str, int]:
    """What DockerLink.frames() polls to decide whether the upcoming pass should
    drain data or trigger a key exchange — see module docstring."""
    return {"chunks_queued": len(_pending_chunks)}


@app.post("/downlink/data")
def next_data_frame() -> dict[str, object]:
    """One call = one encrypted chunk, in sequence-number order. Returns 404 once the
    queue is drained — DockerLink's data-drain loop treats that as "nothing left to
    downlink," the mirror of how it treats a failed /downlink/trigger call for
    KEY_EXCHANGE. Returns *raw* ciphertext — see module docstring for why there's no
    envelope/magic-byte wrapper here."""
    global _next_seq
    if _traffic_key is None:
        raise HTTPException(409, "no active traffic key — complete a key exchange first")
    if not _pending_chunks:
        raise HTTPException(404, "no data queued — call POST /downlink/data/stage first")
    chunk = _pending_chunks.pop(0)
    seq = _next_seq
    _next_seq += 1
    ciphertext = _engine.aead_encrypt(key=_traffic_key, nonce=_nonce_for_seq(seq), plaintext=chunk)
    return {"sequence_number": seq, "ciphertext_hex": ciphertext.hex(), "remaining": len(_pending_chunks)}