# `origo-edge`

The cloud control plane. Postgres-backed REST API: device registry, key/job lifecycle,
the polling surface `origo-station-agent` talks to. Design reference:
[`PQC-HSM-Design.md`](PQC-HSM-Design.md) §1, §6, §9.

## Structure

```
origo-edge/
├── alembic.ini, migrations/            # schema history
├── src/origo_edge/
│   ├── main.py                         # app factory + lifespan (DB engine, DeviceProvisioner)
│   ├── settings.py                     # env-driven config, ORIGO_ prefix
│   ├── clock.py                        # tz-aware time only — see ruff config
│   ├── api/
│   │   ├── deps.py                     # DI: sessions, repos, services, auth, provisioner
│   │   ├── errors.py, middleware.py
│   │   └── v1/{devices,keys,jobs,edge,platform}.py
│   ├── domain/                         # pure logic — no db/api imports
│   │   ├── enums.py                    # DeviceType, KeyState, JobState, ...
│   │   ├── key_lifecycle.py, job_lifecycle.py, transitions.py
│   │   └── errors.py
│   ├── db/
│   │   ├── base.py, session.py
│   │   └── models/{device,key,job}.py
│   ├── repositories/{device,key,job}.py
│   └── services/{key_service,job_service,device_provisioner}.py
└── tests/
    ├── conftest.py                     # testcontainers Postgres
    ├── domain/test_state_machines.py
    ├── test_devices_api.py, test_keys_and_jobs_api.py
    ├── test_edge_status_push.py, test_one_active_key.py
    └── services/test_device_provisioner.py
```

## What's DB-backed vs. still fixtures

`Device`, `Key`, `Job` are real — SQLAlchemy models, Alembic-migrated, served through
`repositories/` → `services/` → `api/v1/`. `api/v1/platform.py` still returns hardcoded
data for passes, telemetry, policies, alerts, and audit — `/overview`'s counts are real
(computed from `Device`/`Key`), everything else there is a fixture pending the same
model → repo → service → route treatment.

## The two route surfaces

- **`api/v1/{devices,keys,jobs}.py`** — human-facing, OIDC in production
  (`ORIGO_AUTH_DISABLED=true` for local dev). What `origo-platform` calls.
- **`api/v1/edge.py`** — machine-facing, behind `require_edge_token`
  (`api/deps.py`) — a shared bearer token standing in for the mTLS device
  authentication the design calls for. `GET /stations/{ref}/job-plans` (pull) and
  `POST /stations/{ref}/status` (push) are what `origo-station-agent`'s Sync Client
  calls — see `PQC-HSM-Design.md` §2 for why this is poll-based, not routed.
  `require_edge_token` honors `settings.auth_disabled` — with no TLS-terminating
  reverse proxy in front of a plain `uv run uvicorn` process locally, there's nothing
  to set the `X-Client-CN` header this route normally requires, so local dev and the
  Docker device loop both depend on this bypass being on.

`{ref}` in edge routes resolves against `Device.serial_number` — an Origo Terrestrial
device's `serial_number` *is* its `station_ref` as far as this API is concerned.

## Domain layer — read this before touching `services/`

`domain/key_lifecycle.py` and `domain/job_lifecycle.py` define the only legal state
transitions (`KEY_MACHINE`, `JOB_MACHINE` — see `PQC-HSM-Design.md` §4 for what each
state means). `services/key_service.py` and `job_service.py` are the only things
permitted to call `.transition()`; nothing constructs a `Key`/`Job` row with a
hand-picked `state` outside them. Two invariants worth knowing about specifically:

- **At most one `ACTIVE` key per device pair**, enforced by a partial unique index in
  `db/models/key.py` — not just checked in Python. `tests/test_one_active_key.py`
  proves the *database* rejects a race, not the service-layer check.
- **At most one in-flight key exchange per pair** (`PENDING_KEYGEN` through
  `DECAPS_COMPLETE`) — a service-layer check in `key_service.create_pending`, since an
  `ACTIVE` key plus a new `PENDING_KEYGEN` one is the normal rekey shape and shouldn't
  be blocked, only genuine duplicates.

`KEY_MACHINE`'s four in-flight states (`PENDING_KEYGEN → EK_SENT → AWAITING_CT →
DECAPS_COMPLETE → ACTIVE`) model a handshake staggered across separately-observed
moments. The system as actually built doesn't have separately-observed moments — a
key exchange reaches `push_status` as exactly one ground-side `job.result` event at
pass end. `api/v1/edge.py`'s fan-out walks all four transitions on that single event
rather than widening the machine to allow a direct jump, so the granular states stay
meaningful for whenever a real per-phase signal exists. A `FAILED` outcome revokes
the key (it's not going to improve on retry, and a stuck `PENDING_KEYGEN` key blocks
any *new* exchange for that device pair via the in-flight check above); a
`TIMED_OUT` outcome deliberately does not — a pass ending before the `ek` arrived
doesn't mean the key is bad, just that this pass didn't carry it.

## The Docker device loop (local dev / demo only)

`services/device_provisioner.py` — when enabled
(`ORIGO_DEVICE_PROVISIONING_ENABLED=true`), registering a device via `POST
/v1/devices` starts a real Docker container for it (`origo-space`/`origo-terrestrial`
+ its paired `origo-station-agent`), and automates the provisioning-key-exchange
ceremony between a newly-registered Origo Terrestrial and the Origo Space device
named in its `peer_serial_number`. Talks to the *local* Docker daemon
(`docker.from_env()`) — this process still runs directly on the host exactly as
`make dev-edge` always has; it just also holds the keys to the host's Docker socket.
Provisioning runs in a threadpool (`starlette.concurrency.run_in_threadpool`), not
inline in the request coroutine — it does real blocking I/O (Docker SDK calls, HTTP
calls to device sidecars, retry `time.sleep()` loops up to ~50s worst case), and
running that directly in an `async def` endpoint would stall the entire event loop
for the whole duration. Full walkthrough, sequence diagram of the provisioning
ceremony, and known limitations: `docs/docker-device-loop.md`.

This is explicitly a local-dev/demo convenience layered on top of the real system —
`§1`'s trust boundaries don't change, and production origo-edge has no business
starting containers for satellite/ground firmware that will eventually be real
hardware.

## Running it

```bash
cp .env.example .env
docker compose up -d postgres redis     # from repo root
uv run alembic upgrade head
uv run uvicorn origo_edge.main:app --reload --port 8000
# or: make dev-edge, from repo root
```

`http://localhost:8000/v1/docs` — interactive OpenAPI docs (disabled when `ORIGO_ENV=prod`).

## Seeding devices without the UI

```bash
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"Aster-1","type":"ORIGO_SPACE","serial_number":"SN-001"}'
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"GS-North","type":"ORIGO_TERRESTRIAL","serial_number":"SN-002","peer_serial_number":"SN-001"}'
```

`peer_serial_number` only matters when `ORIGO_DEVICE_PROVISIONING_ENABLED=true` — it
tells the provisioner which already-running Origo Space container this Origo
Terrestrial should pair with. Origo Space always has to be registered (and running)
first; there's no live channel to negotiate a peer key after the fact, matching the
real trust model in §2, not just a provisioning-order convenience.

Both responses include `container_status` (`"running"` / `"provisioning_failed"` /
`"not_provisioned"`) — a provisioning failure never fails the registration itself;
the device row is the source of truth regardless of whether its container came up.

## Tests

```bash
uv run pytest tests/ -v          # needs Docker running — testcontainers spins up a real Postgres
```

| File | Proves |
|---|---|
| `domain/test_state_machines.py` | Every enum state is reachable in its machine; illegal transitions raise; terminal states have no outgoing edges |
| `test_devices_api.py` | Registration succeeds; duplicate `serial_number` → 409 |
| `test_keys_and_jobs_api.py` | Full register→create-key-exchange→appears-in-job-plans flow; wrong device type rejected; redundant in-flight exchange rejected |
| `test_one_active_key.py` | Two concurrent activations for one pair — exactly one wins, at the database level |
| `test_edge_status_push.py` | A pushed `job.result` event activates the key *and* the job; a data-delivery result is downloadable afterward via `GET /jobs/{id}/result` |
| `services/test_device_provisioner.py` | Provisioning-ceremony ordering (Origo Space must exist first; the peer-key push happens after both identities are fetched); disabled/missing-Docker-SDK no-ops; failures are wrapped and re-raised, never swallowed |

`test_edge_status_push.py` is the one that proves the full loop described in
`PQC-HSM-Design.md` §4 step 8-9 actually persists, not just that each endpoint
responds — **if you're running this after picking up the granular-state-walk fix
above, re-run it specifically**, since it needs to exercise the real single-atomic-
event `push_status` call, not a mocked single-hop `advance()`.

## Migrations

```bash
make revision m="describe the change"    # alembic revision --autogenerate
make migrate                             # alembic upgrade head
```

Always read the autogenerated file before applying — reliable for new tables, worth a
second look for column-type changes on existing ones. `db/models/__init__.py` needs
every model imported for autogenerate to see new tables — this has bitten this repo
before (an incomplete model file with a missing `Base` import silently broke
`alembic upgrade head` for *every* table, not just its own, since `db/models/__init__.py`
imports the whole package eagerly).

## Known gaps

- `/v1/edge/*` auth is a dev token behind an `auth_disabled` bypass, not mTLS.
- `Pass`, `Telemetry`, `ConfigPolicy`, `Alert`, `AuditEvent` — still fixtures in `platform.py`.
- JobPlan `signature` is currently empty — no KMS signing yet. Origo Terrestrial's
  `ApplyConfig` RPC reflects this too (see `origo-terrestrial.md`).
- `db/models/__init__.py` needs every model imported for Alembic autogenerate to see
  new tables — adding a model without adding it there is a silent migration gap.
- **`DeviceProvisioner` is local-dev/demo only** — see "The Docker device loop" above.
  It's disabled by default (`ORIGO_DEVICE_PROVISIONING_ENABLED=false`) precisely so a
  plain `make dev-edge` with no Docker daemon reachable behaves exactly as it always
  has.