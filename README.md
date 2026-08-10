# Origo

A post-quantum-secure satellite command and telemetry platform: ML-KEM key
establishment between a satellite (**Origo Space**) and a ground station (**Origo Terrestrial**), orchestrated by a cloud control plane and a per-station edge agent.
Full architecture and rationale: [`docs/PQC-HSM-Design.md`](docs/PQC-HSM-Design.md).

## The four modules

| Module | What it is | Lives | Docs |
|---|---|---|---|
| `origo-edge` | Cloud control plane — Postgres-backed API, device registry, key/job lifecycle | Cloud | [`docs/origo-edge.md`](docs/origo-edge.md) |
| `origo-platform` | Operator dashboard (React) | Cloud | [`docs/origo-platform.md`](docs/origo-platform.md) |
| `origo-station-agent` | Ground edge agent — runs the live pass protocol | Ground station, same hardware as Origo Terrestrial | [`docs/origo-station-agent.md`](docs/origo-station-agent.md) |
| `origo-info-adapter` | Library wrapping the Infostellar StellarStation API | Imported by `origo-station-agent`, no separate deployment | [`docs/origo-info-adapter.md`](docs/origo-info-adapter.md) |

**Origo Space** (satellite) and **Origo Terrestrial** (ground) — the PQC+HSM+QRNG
modules themselves — are hardware/firmware, not part of this repository. This repo is
everything around them: registry, scheduling, the live RF-facing protocol execution,
and the dashboard.

End-to-end walkthroughs of what the system actually does: [`docs/use-cases.md`](docs/use-cases.md).

## Quickstart

```bash
# 1. Dependencies
uv sync --all-packages --all-extras
cd origo-platform && npm ci && cd ..

# 2. Local infrastructure
docker compose up -d
docker compose ps    # postgres and redis both healthy before continuing

# 3. Database
cd origo-edge && cp .env.example .env && uv run alembic upgrade head && cd ..

# 4. gRPC stubs
make proto          # StellarStation — needs the real protos vendored first, see
                     # docs/origo-info-adapter.md if proto/stellarstation/ is empty
make proto-origo     # Origo Terrestrial interface — no external dependency

# 5. Backend
make dev-edge        # http://localhost:8000 — docs at /v1/docs

# 6. Seed two devices (or use the UI's "Register device" once it's running)
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"Aster-1","type":"ORIGO_SPACE","serial_number":"SN-001"}'
curl -X POST localhost:8000/v1/devices -H 'content-type: application/json' \
  -d '{"name":"GS-North","type":"ORIGO_TERRESTRIAL","serial_number":"SN-002"}'

# 7. Frontend
make dev-ui           # http://localhost:5173

# 8. Station agent (needs Origo Terrestrial reachable on its local socket — see
#    docs/origo-station-agent.md)
cd origo-station-agent && cp .env.example .env && uv run python -m origo_station_agent.main
```

**Smoke test:** open `localhost:5173`, confirm both seeded devices appear under
Devices, use *New request* to create a key exchange between them, confirm it appears
in Jobs as `scheduled`. That row reaching Postgres via origo-edge's REST API is the
part this quickstart proves; the rest of the loop (station-agent picking it up,
running the pass, the result coming back) is covered in
[`docs/use-cases.md`](docs/use-cases.md).

## Testing

```bash
make test              # origo-edge + origo-info-adapter unit tests — no network, no creds
make test-int           # origo-info-adapter against real StellarStation — needs QA credentials
cd origo-station-agent && uv run pytest tests/ -v
cd origo-platform && npm test
```

Per-module test coverage and what each suite actually proves is documented alongside
each module — see the table above.

## Repository conventions

- Python: `uv` workspace (`origo-edge`, `origo-info-adapter`, `origo-station-agent`),
  ruff (strict, including `DTZ` — naive-datetime use is a lint failure, not a style
  note) and mypy strict mode. `make lint` / `make fmt`.
- TypeScript: `origo-platform`, Vite + Vitest, ESLint with a feature-boundary rule
  (a `features/` slice may not import from a sibling slice).
- API contract: `make openapi` regenerates `docs/openapi.json` and the frontend's
  generated TypeScript types together — `make contracts` is the CI gate that fails if
  they've drifted from what's committed.
- Every cross-process boundary in this system (dashboard↔edge, edge↔station-agent,
  station-agent↔Origo Terrestrial, adapter↔StellarStation) is documented in
  `docs/PQC-HSM-Design.md` §... — worth reading before adding a fifth one. of an API or XPI