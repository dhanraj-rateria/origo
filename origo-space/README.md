# `origo-space`

The satellite-side PQC module — a **software stand-in** for firmware that doesn't
exist yet. Design reference: [`PQC-HSM-Design.md`](PQC-HSM-Design.md) §1, §5.2.

## Structure

```
origo-space/
├── Dockerfile                    # vendors a validated wolfSSL build — see origo-crypto.md
├── src/origo_space/
│   ├── agent.py                  # OrigoSpaceAgent — the crypto flow itself
│   ├── identity.py               # IdentityStore — this device's own keypair
│   └── server.py                 # FastAPI wrapper — makes this runnable as a container
└── tests/
    └── test_server.py            # real ML-KEM/ML-DSA roundtrip + multi-frame data delivery
```

## What's real here, and what isn't

`agent.py`, `identity.py`, and the crypto they call in `origo_crypto` are the real
thing — the same `WolfCryptEngine` calls a real satellite's firmware would make.
`server.py` is not real: no actual satellite is reachable over HTTP (design §2's "no
live channel... in either direction" is exactly the point). It exists purely so this
process can run as its own container and be reached by
`origo_info_adapter.dockerlink` — the Docker device loop's substitute for a real RF
downlink/uplink. See `docs/docker-device-loop.md` for the full picture; nothing in
this file changes for whenever real firmware eventually exists — `server.py` is what
gets deleted at that point, not `agent.py`/`identity.py`.

## `identity.py` — independent on purpose

`IdentityStore` persists this device's own ML-DSA-87 keypair to a local file and
generates one if it doesn't exist yet. It's deliberately **not** imported from
`origo_terrestrial` — same shape (`agent.py`'s own comment says so), separate
implementation, because Origo Space and Origo Terrestrial are separate trust
boundaries in separate physical locations. One never imports the other's package,
even in this software prototype.

## `server.py` — the HTTP surface

| Route | What it stands in for |
|---|---|
| `GET /health` | container liveness — Docker `HEALTHCHECK`, provisioner's wait-until-ready poll |
| `GET /identity` | this device's public key, for the provisioning ceremony (§9) |
| `POST /peer` | receiving the paired Origo Terrestrial's public key — the provisioner calls this once, after both containers exist |
| `POST /downlink/trigger` | §5.2 steps 3-4: KeyGen + sign `ek`, "transmit" it |
| `POST /uplink` | §5.2 step 7: verify + Decapsulate the returned `ct` |
| `POST /downlink/data/stage` | queue a plaintext payload for encrypted downlink (DATA_DELIVERY demo) |
| `POST /downlink/data` | hand back the next queued, AES-256-GCM-encrypted chunk |
| `GET /downlink/data/status` | how many chunks remain — what `DockerLink.frames()` polls to decide whether a pass should drain data or trigger a key exchange |

The traffic key derived in `/uplink` never leaves this process — `/uplink` returns a
SHA-256 fingerprint of it, not the key itself, the same rule `KemKeypair.dk`'s own
docstring states for the private key.

## Data delivery: raw ciphertext, no envelope wrapper — and why

`/downlink/data` returns bare AES-256-GCM ciphertext, nothing else — no magic bytes,
no embedded sequence number. That's a hard constraint, not a simplification:
`origo_station_agent.pass_executor._run_data_delivery` tracks its own sequence
number locally (0, 1, 2... in the order frames arrive) and hands it straight to Origo
Terrestrial's `DecryptPayload` as the nonce source — it never reads a sequence
number out of the frame itself. Wrapping the ciphertext in anything else would just
be extra bytes `DecryptPayload` doesn't expect and would fail to authenticate.

The one thing this pushes onto `stage_data()`: the sequence counter **must** reset to
0 at the start of every new staged batch, since the consumer's counter resets to 0 for
every fresh `DATA_DELIVERY` step. `stage_data()` enforces one batch in flight at a
time for exactly that reason — staging a second batch before the first fully drains
returns `409`, rather than silently producing ciphertext the next job's decrypt would
fail to authenticate.

## Running it

```bash
uv run uvicorn origo_space.server:app --host 0.0.0.0 --port 8080
```

Env vars: `ORIGO_SPACE_DEVICE_ID` (default `aster-1`), `ORIGO_SPACE_IDENTITY_PATH`
(default `identity.json`, relative to CWD — point this at a mounted volume in
Docker, not at the container's ephemeral filesystem).

Via the Docker device loop, this container is started automatically by
`origo-edge`'s `DeviceProvisioner` on `POST /v1/devices` with
`type=ORIGO_SPACE` — see `docs/docker-device-loop.md`. Manual single-container run:

```bash
mkdir -p vendor/wolfssl/lib vendor/wolfssl/include   # see origo-crypto.md
docker build -f origo-space/Dockerfile -t origo-space:latest .
docker run -p 8080:8080 -e ORIGO_SPACE_DEVICE_ID=sn-001 origo-space:latest
```

## Tests

```bash
uv run pytest origo-space/tests -v
```

| Case | Proves |
|---|---|
| Full roundtrip | A real ML-KEM-1024 + ML-DSA-87 handshake against a simulated terrestrial side (built directly on `origo_crypto`, not importing `origo_terrestrial` — same module-independence rule as production code), then a multi-chunk staged payload drained and decrypted back to the original plaintext |
| `/uplink` without a peer key | `409`, not a crash |
| Invalid hex on `/peer`/`/uplink` | `400` |
| Staging a second batch before the first drains | `409` — the sequence-counter-reset guard |
| Draining past the end of the queue | `404` |

Simulates the terrestrial side directly against `WolfCryptEngine` rather than
importing `origo_terrestrial`, matching this package's own rule about not depending
on it.

## Known gaps

- **Single-key, single-peer scope.** `_peer_public_key`/`_traffic_key` are process-
  global, not per-connection — this process represents exactly one satellite talking
  to exactly one ground station at a time, matching the demo's scope, not a
  multi-tenant model.
- **`frames()`'s dual-mode heuristic lives in `origo_info_adapter.dockerlink`, not
  here** — this process has no opinion about whether the next HTTP call is "for" a
  key exchange or a data delivery; it just answers whichever endpoint gets called.
  See that package's docs for the actual limitation (a station-agent container can't
  run a fresh key exchange during a pass where data happens to be staged).
- **Identity persistence is tied to the container's own named volume**, which
  `DeviceProvisioner` derives deterministically from `serial_number` — re-registering
  the same serial number reuses the same volume and therefore the same identity. Not
  a bug (verified by tracing the actual naming function), but worth knowing if you
  ever change how the provisioner names volumes.