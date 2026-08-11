# `origo-station-agent`

The ground edge agent (design doc §2). Runs at each ground-station site, co-located
with Origo Terrestrial on the same physical hardware — or, in the Docker device loop,
its own container paired 1:1 with an Origo Terrestrial container on a shared Docker
network. Talks to `origo-edge` on one side (poll job plans, push results), Origo
Terrestrial and StellarStation (via `origo-info-adapter`) on the other. Design
reference: [`PQC-HSM-Design.md`](PQC-HSM-Design.md) §2–§4, §7.

## Structure

```
origo-station-agent/
├── Dockerfile                          # no wolfCrypt here — this process does no cryptography
├── proto/origo/v1/origo.proto          # OrigoTerrestrialService — this repo's own interface
├── src/origo_station_agent/
│   ├── main.py                         # entrypoint: poll loop + pass triggering
│   ├── settings.py
│   ├── models.py                       # JobPlan / JobPlanStep
│   ├── errors.py
│   ├── events.py                       # StepResult -> wire events for push_status
│   ├── pass_executor.py                # the state machine that runs a live pass
│   ├── sync_client.py                  # talks to origo-edge
│   └── origo/{ports.py, grpc_client.py} # talks to Origo Terrestrial
└── tests/
    ├── fake_origo.py
    └── test_pass_executor.py
```

## The three links this process owns

- **`sync_client.py` ↔ `origo-edge`** — REST, device-token auth (mTLS in the design;
  `ORIGO_AUTH_DISABLED` on the origo-edge side is what actually lets this work without
  real certs in local dev and in the Docker device loop — see `origo-edge.md`).
  `fetch_job_plans()` (pull, `GET .../job-plans`) and `push_status()` (push,
  `POST .../status`). See `PQC-HSM-Design.md` §2 — this is genuinely poll-based, not a
  route origo-edge pushes through.
- **`origo/grpc_client.py` ↔ Origo Terrestrial** — gRPC, over a Unix domain socket by
  default (`unix:///var/run/origo/origo-terrestrial.sock`, same physical hardware) or
  over TCP when `ORIGO_STATION_ORIGO_ENDPOINT` points at a `host:port` instead — the
  Docker device loop always uses TCP, since separate containers have no shared
  filesystem for a Unix socket. `GrpcOrigoTerrestrial` implements the `OrigoTerrestrial`
  protocol from `origo/ports.py` against `proto/origo/v1/origo.proto`'s
  `OrigoTerrestrialService`.
- **`origo_info_adapter` (imported, not a network call from this process's own
  perspective)** — used directly inside `pass_executor.py` via the
  `GroundNetworkAdapter`/`ContactLink` interface it exports. In the Docker device
  loop, `ORIGO_RF_LINK_URL` (an `origo_info_adapter` env var, set on this container)
  selects `DockerLinkAdapter`, which *does* make its own HTTP calls to an Origo Space
  container — but that's the adapter's concern; `pass_executor.py` still just calls
  `open_link()`/`frames()`/`send_commands()` on whatever `build_adapter()` returned.

## `pass_executor.py` — what actually runs during a pass

`PassExecutor.run(plan, contact_id, now)` opens a `ContactLink` through the adapter and
walks each `JobPlanStep`:

- **`KEY_EXCHANGE`**: waits on `link.frames()` for a frame matching the KEM envelope
  format (magic-tagged, length-prefixed — see `_parse_kem_envelope`/`_frame_ct`),
  hands `ek`+signature to Origo Terrestrial via `verify_and_encapsulate`, uplinks the
  resulting `ct`+signature via `link.send_commands()`.
- **`DATA_DELIVERY`**: decrypts each downlink frame via `decrypt_payload`, tracking its
  own sequence number locally (0, 1, 2... in the order frames arrive — not read out of
  the frame itself), accumulates plaintext, and reports `frame_count` plus the
  concatenated bytes in the step result. `main.py`'s sync loop is what turns
  `detail["plaintext"]` (raw bytes) into `detail["plaintext_b64"]` for the JSON push to
  origo-edge — that boundary is where the base64 encoding actually happens, not here.
- **`CONFIG_PUSH`**: hands a signed config blob to `apply_config` — Origo Terrestrial
  verifies the signature itself; this call is delivery, not a trust decision made here.
  (Origo Terrestrial's current `ApplyConfig` is a placeholder — see `origo-terrestrial.md`.)

Every step gets its own `timeout_sec`; a step that doesn't resolve in time is marked
`TIMED_OUT` and left for `origo-edge` to reschedule on a later pass — never retried
mid-pass, so one stuck step can't consume the rest of a short contact window.

## The envelope framing (`_parse_kem_envelope` / `_frame_ct`)

A minimal, deliberately unclever format: 4-byte magic (`OSKX`), then each field
(`ek`, signature, device id, nonce) as a 4-byte big-endian length prefix followed by
the bytes. This is the one piece of this repo with no existing external convention to
match — it's a contract between this code and whatever Origo Terrestrial's firmware
implements on the other end, so both sides need to agree on it explicitly (it isn't
derivable from the `.proto`, since the envelope travels *inside* a `DownlinkFrame`'s
opaque `data` field, not as a typed gRPC message). `DATA_DELIVERY` frames carry no
equivalent wrapper — see `origo-space.md` for why raw ciphertext is correct there.

## Running it

```bash
cp .env.example .env
sudo mkdir -p /var/run/origo && sudo chmod 750 /var/run/origo   # Origo Terrestrial's own
                                                                  # process must bind here first
make proto-origo         # from repo root — generates the Origo Terrestrial *client* stubs
uv run python -m origo_station_agent.main
```

`make proto-origo` post-processes the generated `*_pb2_grpc.py` to fix a
`grpc_tools.protoc` quirk: it emits an absolute sibling import
(`from origo.v1 import origo_pb2`) that raises `ModuleNotFoundError` the moment
anything imports the stub, since there's no real top-level `origo` package. The fix
(rewrite to a relative import) lives in `scripts/gen_proto.py` itself now, not as a
manual step — this broke `test_end_to_end_key_exchange.py`'s collection once already.

Until real firmware exists, point `ORIGO_STATION_ORIGO_ENDPOINT` at a local mock gRPC
server implementing `OrigoTerrestrialService` (the same fake used in tests,
`tests/fake_origo.py`, can be served over a real socket for a manual end-to-end run
without waiting on hardware) — or, for the full Docker device loop, let
`origo-edge`'s `DeviceProvisioner` start this container automatically, paired with a
real (software-stand-in) Origo Terrestrial container. See `docs/docker-device-loop.md`.

## Tests

```bash
uv run pytest tests/ -v
```

Uses `origo_info_adapter.fake.adapter.InMemoryAdapter` — the real adapter package,
fake ground-network backend — plus a hand-written `FakeOrigoTerrestrial`. This is
deliberately the same pattern as `origo-info-adapter`'s own fake: same awkward
semantics as production (rejects on demand), not a kinder version.

| Case | Proves |
|---|---|
| Key exchange succeeds | `ek` parsed correctly, `verify_and_encapsulate` called once, `ct` uplinked in the expected wire format |
| Key exchange rejected by Origo Terrestrial | Step outcome `FAILED`, and — the assertion that matters — nothing gets uplinked after a rejection |
| Data delivery, all frames decrypt | Plaintext concatenated in order, `frame_count` correct |
| Data delivery, fails partway | `FAILED` with `bytes_before_failure` reflecting only the frames that succeeded before the failure |
| Stale plan | `JobPlanStale` raised *before* `adapter.open_link` is ever called |

The full, real-crypto version of the key-exchange case (real `WolfCryptEngine` on both
sides, a real in-process gRPC server, real `PassExecutor`/`GrpcOrigoTerrestrial`) lives
at the repo root as `tests/test_end_to_end_key_exchange.py`, not in this package's own
`tests/` — it deliberately spans `origo-crypto`, `origo-space`, `origo-terrestrial`, and
this package in one process.

## Known gaps

- **AOS triggering** uses the JobPlan's own `valid_from` as the trigger — a real,
  working default, not a stub, but not tied to actual antenna-controller hardware. A
  site with a real AOS signal (GPIO, controller event) should feed it into the same
  `now < plan.valid_from` check in `main.py` rather than replacing the mechanism.
- **`push_status` failures are logged, not durably retried** — a push that fails after
  a pass currently just logs and moves on; a local durable queue (retry on the next
  poll cycle) is the honest next step, not yet built.
- **mTLS** for the `origo-edge` link is a device-cert pair in settings today; the
  server side enforces this via a dev-only `ORIGO_AUTH_DISABLED` bypass, not real
  mTLS — see `origo-edge.md`. The Docker device loop's container image generates a
  self-signed placeholder cert/key at build time purely so `SyncClient`'s
  `httpx.AsyncClient` can construct at all (it loads cert files into an `SSLContext`
  eagerly regardless of whether origo-edge ends up being plain HTTP or HTTPS) — not a
  real credential, not meant to be one.
- **`DockerLinkAdapter`'s `frames()` heuristic** (see `origo-info-adapter.md`) means a
  station-agent container in the Docker device loop can't run a fresh key exchange
  during a pass where data happens to be staged. Real RF and `InMemoryAdapter` don't
  have this limitation; it's specific to the Docker mock.