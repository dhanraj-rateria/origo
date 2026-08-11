# Origo

A post-quantum-secure satellite command and telemetry platform: ML-KEM key
establishment between a satellite (**Origo Space**) and a ground station (**Origo
Terrestrial**), orchestrated by a cloud control plane and a per-station edge agent.
Full architecture and rationale: [`docs/PQC-HSM-Design.md`](docs/PQC-HSM-Design.md).

## The six modules

| Module | What it is | Lives | Docs |
|---|---|---|---|
| `origo-edge` | Cloud control plane — Postgres-backed API, device registry, key/job lifecycle | Cloud | [`docs/origo-edge.md`](docs/origo-edge.md) |
| `origo-platform` | Operator dashboard (React) | Cloud | [`docs/origo-platform.md`](docs/origo-platform.md) |
| `origo-station-agent` | Ground edge agent — runs the live pass protocol | Ground station, same hardware as Origo Terrestrial (or its own container in the Docker device loop) | [`docs/origo-station-agent.md`](docs/origo-station-agent.md) |
| `origo-info-adapter` | Library wrapping ground-network providers (StellarStation; a Docker-only mock) behind one interface | Imported by `origo-station-agent`, no separate deployment | [`docs/origo-info-adapter.md`](docs/origo-info-adapter.md) |
| `origo-crypto` | The PQC engine — ML-KEM-1024, ML-DSA-87, AES-256-GCM, HKDF over wolfCrypt | Imported by `origo-space` and `origo-terrestrial` | [`docs/origo-crypto.md`](docs/origo-crypto.md) |
| `origo-space` | Satellite-side PQC module | Software stand-in today — see below | [`docs/origo-space.md`](docs/origo-space.md) |
| `origo-terrestrial` | Ground-side PQC HSM module | Software stand-in today — see below | [`docs/origo-terrestrial.md`](docs/origo-terrestrial.md) |

**Origo Space** and **Origo Terrestrial** are, in the eventual real system,
PQC+HSM+QRNG hardware/firmware — not something this repo builds or ever will. What
this repo *does* include are software stand-ins for both, sharing the real
`origo-crypto` engine that real firmware would use, so the actual ML-KEM/ML-DSA
handshake — and now a full encrypted data-delivery round trip — can be exercised end
to end without hardware. They run as real, separate Docker containers exchanging real
key material over a real (if RF/StellarStation-mocked) link — see
[`docs/docker-device-loop.md`](docs/docker-device-loop.md) for the full picture.
Nothing about this changes what origo-edge, origo-station-agent, or
origo-info-adapter are allowed to touch in the real system; it's local
infrastructure for developing and demoing against, not a production deployment model.

End-to-end walkthroughs of what the system actually does: [`docs/use-cases.md`](docs/use-cases.md).

## Quickstart

Steps 1–7 are shared. After that, pick **Path A** (recommended — origo-space and
origo-terrestrial run as real containers, everything wired automatically) or
**Path B** (manual, single station, closer to what a real firmware deployment will
eventually look like).

### 1. Dependencies

```bash
uv sync --all-packages --all-extras
cd origo-platform && npm ci && cd ..
```

### 2. gRPC stubs — three separate generation steps, three different packages

```bash
make proto              # StellarStation client stubs — needs the real protos vendored
                         # first; see docs/origo-info-adapter.md if proto/stellarstation/
                         # is empty
make proto-origo         # Origo Terrestrial *client*-side stubs, for origo-station-agent
make proto-terrestrial   # Origo Terrestrial *server*-side stubs, for origo-terrestrial
                         # itself — same .proto contract, deliberately regenerated
                         # independently on each side, see docs/origo-terrestrial.md
```

Both `proto-origo` and `proto-terrestrial` post-process the generated
`*_pb2_grpc.py` to fix a `grpc_tools.protoc` quirk (an absolute sibling import that
raises `ModuleNotFoundError: No module named 'origo'` otherwise) — this is handled
inside the generation scripts now, not a manual step.

### 3. wolfSSL — required before touching `origo-crypto`, `origo-space`, or `origo-terrestrial`

This repo doesn't build wolfSSL for you. You need a compiled `libwolfssl.so` with
ML-KEM-1024, ML-DSA-87 (`*Ctx` sign/verify variants), AES-GCM, and HKDF support
reachable by `ctypes.CDLL("libwolfssl.so")` (typically `/usr/local/lib`). Confirm it
actually works before going further — a broken or mismatched build fails loudly but
unhelpfully three layers downstream otherwise:

```bash
uv run python -c "
from origo_crypto.wolfcrypt_engine import WolfCryptEngine
e = WolfCryptEngine()
print('kem', len(e.kem_keygen().ek), 'dsa', len(e.dsa_keygen()[0]),
      'hkdf', len(e.hkdf(shared_secret=b'x'*32, context=b'test')))
"
# expect: kem 1568 dsa 2592 hkdf 32
```

If `hkdf` raises `wolfCrypt wc_HKDF failed, rc=-173`, your build's `WC_SHA256`
constant isn't `6` (this codebase's confirmed value, not a portable one) — see
`docs/origo-crypto.md` for the diagnostic script that finds the right number for
your specific build.

### 4. Prove the crypto path end to end — zero containers

```bash
uv run pytest tests/test_end_to_end_key_exchange.py -v
```

Real `WolfCryptEngine` on both sides, real ML-KEM-1024/ML-DSA-87, a real in-process
gRPC server — everything the rest of this quickstart depends on, provable in under a
second with nothing else running.

### 5. Local infrastructure

```bash
docker compose up -d
docker compose ps    # postgres and redis both healthy before continuing
```

### 6. Database

```bash
cd origo-edge && cp .env.example .env
```

Edit `.env`:
- `ORIGO_AUTH_DISABLED=true` — required for local dev either path; without it every
  `/v1/edge/*` call (station-agent ↔ edge) 401s, since nothing locally sets the
  `X-Client-CN` header the design's real mTLS path expects.
- `ORIGO_DEVICE_PROVISIONING_ENABLED=true` — **only if you're doing Path A** below.
  Leave `false` for Path B.

```bash
uv run alembic upgrade head
uv run alembic current   # confirm it's at head before continuing
cd ..
```

### 7. Backend

```bash
make dev-edge        # http://localhost:8000 — docs at /v1/docs
```

---

### Path A: Docker device loop (recommended)

Vendor a working wolfSSL build into the Docker context and build the three device
images (this reuses the exact `.so` you validated in step 3, rather than re-deriving
`./configure` flags — see `docs/origo-crypto.md` for why that distinction matters):

```bash
mkdir -p vendor/wolfssl/lib vendor/wolfssl/include
cp -a /usr/local/lib/libwolfssl.so* vendor/wolfssl/lib/
cp -r /usr/local/include/wolfssl    vendor/wolfssl/include/wolfssl
make images
```

Register two devices — this starts real containers automatically:

```bash
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"Aster-1","type":"ORIGO_SPACE","serial_number":"SN-001"}'
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"GS-North","type":"ORIGO_TERRESTRIAL","serial_number":"SN-002","peer_serial_number":"SN-001"}'
docker ps   # origo-space-sn-001, origo-terrestrial-sn-002, origo-station-agent-sn-002
```

`peer_serial_number` — the Origo Space device it pairs with — is required for a
Terrestrial registration under this path, and that device must already be
registered and running: there's no live channel to negotiate a peer key after the
fact, matching the real trust model, not just a provisioning-order convenience.

Drive a real key exchange between them (use the `id` values from the two responses
above):

```bash
curl -X POST localhost:8000/v1/jobs -H 'content-type: application/json' \
  -d '{"type":"KEY_EXCHANGE","satellite_device_id":"<SN-001 id>","ground_device_id":"<SN-002 id>"}'
```

Within ~60s:

```bash
docker exec origo-postgres-1 psql -U postgres -d origo -c "SELECT id, state FROM jobs;"
docker exec origo-postgres-1 psql -U postgres -d origo -c "SELECT id, state, hsm_key_reference FROM keys;"
```

Both should read `ACTIVE`. Full walkthrough (provisioning-ceremony sequence diagram,
data-delivery encrypt/decrypt round trip, known limitations):
[`docs/docker-device-loop.md`](docs/docker-device-loop.md).

### Path B: Manual / single station

Closer to what a real firmware deployment eventually looks like — one
origo-station-agent process, talking to one Origo Terrestrial reachable on a local
socket, not containerized.

```bash
sudo mkdir -p /var/run/origo && sudo chmod 750 /var/run/origo
```

Start Origo Terrestrial's own software stand-in (or point at real firmware, once it
exists):

```bash
cd origo-terrestrial && uv run python -m origo_terrestrial.server
```

In another terminal:

```bash
cd origo-station-agent && cp .env.example .env
uv run python -m origo_station_agent.main
```

Seed the same two devices as Path A (omit `peer_serial_number` — it's only read when
`ORIGO_DEVICE_PROVISIONING_ENABLED=true`):

```bash
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"Aster-1","type":"ORIGO_SPACE","serial_number":"SN-001"}'
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"GS-North","type":"ORIGO_TERRESTRIAL","serial_number":"SN-002"}'
```

`ORIGO_STATION_ORIGO_ENDPOINT` needs to point at whatever's actually serving
`OrigoTerrestrialService` — this repo's own software stand-in above, `tests/fake_origo.py`
served over a real socket, or eventually real firmware.

---

### 8. Frontend (either path)

```bash
make dev-ui           # http://localhost:5173
```

**Smoke test:** open `localhost:5173`, confirm both seeded devices appear under
Devices (Path A: with a green/running container indicator; Path B: without one),
use *New request* to create a key exchange between them, confirm it appears in Jobs
as `scheduled` and then, within a minute, `active`. Path A additionally lets you
confirm this against real Docker containers and Postgres directly, per the commands
above — Path B's confirmation is the platform UI and `origo-station-agent`'s own logs.

## Testing

```bash
make test                                                    # origo-edge + origo-info-adapter unit tests — no network, no creds
make test-int                                                 # origo-info-adapter against real StellarStation — needs QA credentials
uv run pytest tests/test_end_to_end_key_exchange.py -v         # real crypto, zero containers
uv run pytest origo-space origo-info-adapter/tests origo-edge/tests -v   # the newer modules' own suites
cd origo-station-agent && uv run pytest tests/ -v
cd origo-platform && npm test
```

Per-module test coverage and what each suite actually proves is documented alongside
each module — see the table above.

## Repository conventions

- Python: `uv` workspace (`origo-edge`, `origo-info-adapter`, `origo-station-agent`,
  `origo-crypto`, `origo-space`, `origo-terrestrial`), ruff (strict, including `DTZ` —
  naive-datetime use is a lint failure, not a style note) and mypy strict mode.
  `make lint` / `make fmt` currently cover `origo-edge` and `origo-info-adapter`;
  `origo-crypto`/`origo-space`/`origo-terrestrial` aren't in that gate yet — worth
  fixing before they see much more change.
- TypeScript: `origo-platform`, Vite + Vitest, ESLint with a feature-boundary rule
  (a `features/` slice may not import from a sibling slice).
- API contract: `make openapi` regenerates `docs/openapi.json` and the frontend's
  generated TypeScript types together — `make contracts` is the CI gate that fails if
  they've drifted from what's committed.
- Docker images (`origo-space`, `origo-terrestrial`, `origo-station-agent`) vendor a
  validated wolfSSL build rather than compiling one with guessed `./configure` flags
  — see `docs/origo-crypto.md` for why that distinction is load-bearing, not just a
  preference.
- Every cross-process boundary in this system (dashboard↔edge, edge↔station-agent,
  station-agent↔Origo Terrestrial, adapter↔StellarStation, and — local-dev only —
  edge↔Docker daemon, station-agent↔Origo Space over the mocked RF link) is
  documented in `docs/PQC-HSM-Design.md` and `docs/docker-device-loop.md` — worth
  reading before adding a sixth.