# `origo-edge`

The cloud control plane. Postgres-backed REST API: device registry, key/job lifecycle,
the polling surface `origo-station-agent` talks to. Design reference:
[`PQC-HSM-Design.md`](PQC-HSM-Design.md) §1, §6, §9.

## Structure

```
origo-edge/
├── alembic.ini, migrations/            # schema history
├── src/origo_edge/
│   ├── main.py                         # app factory + lifespan (DB engine)
│   ├── settings.py                     # env-driven config, ORIGO_ prefix
│   ├── clock.py                        # tz-aware time only — see ruff config
│   ├── api/
│   │   ├── deps.py                     # DI: sessions, repos, services, auth
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
│   └── services/{key_service,job_service}.py
└── tests/
    ├── conftest.py                     # testcontainers Postgres
    ├── domain/test_state_machines.py
    ├── test_devices_api.py, test_keys_and_jobs_api.py
    ├── test_edge_status_push.py, test_one_active_key.py
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
  -d '{"name":"GS-North","type":"ORIGO_TERRESTRIAL","serial_number":"SN-002"}'
```

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

`test_edge_status_push.py` is the one that proves the full loop described in
`PQC-HSM-Design.md` §4 step 8-9 actually persists, not just that each endpoint responds.

## Migrations

```bash
make revision m="describe the change"    # alembic revision --autogenerate
make migrate                             # alembic upgrade head
```

Always read the autogenerated file before applying — reliable for new tables, worth a
second look for column-type changes on existing ones.

## Known gaps (tracked, not hidden)

- `/v1/edge/*` auth is a dev token, not mTLS.
- `Pass`, `Telemetry`, `ConfigPolicy`, `Alert`, `AuditEvent` — still fixtures in `platform.py`.
- JobPlan `signature` is currently empty — no KMS signing yet.
- `db/models/__init__.py` needs every model imported for Alembic autogenerate to see
  new tables — adding a model without adding it there is a silent migration gap.