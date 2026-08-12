# `origo-stellarstation-mock`

A real, protocol-accurate StellarStation emulator for the Docker device loop —
implements the actual `stellarstation.proto` `OpenSatelliteStream` bidi-streaming
RPC, relaying to a registered Origo Space container. `origo-station-agent` runs its real, unmodified
`StellarStationAdapter`/`StellarStationLink` client against this, the same code path
that would run against Infostellar's real cloud API. Design reference:
[`docs/docker-device-loop.md`](docker-device-loop.md).

## Structure

```
origo-stellarstation-mock/
├── Dockerfile
├── certs/
│   ├── server.crt, server.key       # static, shared, self-signed — see below
│   └── fake-service-account.json    # real RSA key, fake identity — see below
├── pyproject.toml                   # depends on origo-info-adapter for its generated stubs
└── src/origo_stellarstation_mock/
    └── server.py
```

## Why this exists instead of extending the custom REST mock

The original device loop used `origo_info_adapter.dockerlink.DockerLinkAdapter` — a
custom REST shape invented for the demo. It worked, but `origo-station-agent` was
then running code that would never resemble what happens against the real API. This
package replaces that: a real gRPC server against the real generated protobuf stubs,
so the client side is the actual production code path. `dockerlink/` remains in the
tree, unused, as a rollback path.

## `OpenSatelliteStream` — read `docs/debugging-journal.md` before touching this

This RPC took five real, distinct bugs to get right (#18–#22 in the journal), and
the current shape is a direct result of what those bugs forced:

- **Reads exclusively from `request_iterator`**, never `context.read()`. Mixing the
  two silently deadlocked the read path — the stream would open, then sit completely
  idle until gRPC's own `too_many_pings` flood protection killed it minutes later, a
  symptom with nothing to do with the actual cause.
- **`Telemetry`, `Framing`, `StreamEvent`, and `CommandSentFromGroundStation`** are
  all in `transport_pb2`, not `stellarstation_pb2` — misattributed twice during
  development from eyeballing proximity to file boundaries in a text dump instead of
  checking exact line ranges. Import both modules (`ss` and `tp`) and know which is
  which; don't assume from adjacency.
- **Every task spawned via `asyncio.create_task()` is wrapped in a `guarded()`
  helper** that logs the full traceback and re-raises. `asyncio.wait()` does not
  propagate exceptions from the futures it waits on — without this wrapper, bugs
  #18/#19 above would have looked identical to the ping-flood hang, with zero
  visibility into the real cause. This is what actually found them.
- **One-shot relay, not a continuous feed.** `relay_downlink()` represents "the
  satellite is reachable right now," not real RF telemetry — it checks
  `/downlink/data/status` on the registered Origo Space container; if data is
  staged, drains it as `DATA_DELIVERY` frames; otherwise calls `/downlink/trigger`
  once for `KEY_EXCHANGE`. This is a heuristic, not a real job-type signal — see
  "Known limitation" below.

## Admin/relay API

| Route | Purpose |
|---|---|
| `POST /admin/satellites/{id}` | Register which Origo Space container `{id}` (a satellite_id, i.e. serial number) relays to |
| `DELETE /admin/satellites/{id}` | Unregister |
| `GET /admin/satellites/{id}/health` | Relayed to Origo Space's `/health` — origo-edge's `DeviceProvisioner` calls this instead of Origo Space directly |
| `GET /admin/satellites/{id}/identity` | Relayed to `/identity` |
| `POST /admin/satellites/{id}/peer` | Relayed to `/peer` |
| `GET /health` | This container's own liveness |

**Every one of these exists so that nothing else in the system ever needs to call
Origo Space directly** — not the operational RF/StellarStation path, and not
origo-edge's provisioning ceremony either. Verify with
`grep -rn "origo-space" origo-edge/src` — every real hit should be inside
`device_provisioner.py`, calling this admin API, never a direct `origo-space-*` URL.

## TLS and JWT — a real, deliberate design choice, not a shortcut

`StellarStationSettings.insecure=true` is correctly restricted to loopback endpoints
(`config.py`'s own safety check) — container-to-container traffic never qualifies,
so this mock uses genuine TLS rather than weakening that check:

- **`certs/server.crt`/`server.key`** — a single, static, self-signed certificate,
  CN/SAN = the fixed symbolic name `origo-stellarstation-mock` (not any real
  container hostname, which varies per deployment: `origo-stellarstation-sn-002`,
  `-sn-005`, ...). `origo-station-agent`'s channel sets
  `ORIGO_STELLARSTATION_TLS_SERVER_NAME_OVERRIDE=origo-stellarstation-mock` to match
  regardless of which actual hostname it dials. Not a secret — it doesn't protect
  anything real; committing it is fine.
- **`certs/fake-service-account.json`** — shaped exactly like a real Google
  service-account key, with a **genuine RSA private key** —
  `google_auth_jwt.Credentials.from_service_account_file()` actually parses and
  signs with it (real cryptography, not a placeholder string). It just never leaves
  the container, and this mock's gRPC server accepts the connection on TLS alone
  without verifying the JWT's signature — a deliberate simplification: faking
  Google's own public-key infrastructure server-side would be disproportionate for a
  local mock.
- **`origo-info-adapter`'s `channel.py`/`config.py`** gained two small, additive
  fields to make this possible: `ca_bundle_path` (trust this CA instead of the
  system default store) and `tls_server_name_override`. Both default to `None`,
  meaning zero behavior change for the real production path — see
  `docs/origo-info-adapter.md`.

## Booking/discovery RPCs — deliberately unimplemented

`ListPlans`, `ReservePass`, `CancelPlan`, `ListUpcomingAvailablePasses`, `AddTle`,
`GetTle`, `SetTleSource`, `SetPlanMetadata` are stubbed (empty responses or
`UNIMPLEMENTED`), not because they're unimportant but because nothing in this
system's actual runtime path calls them — `PassExecutor.run()` is handed a `JobPlan`
directly by origo-edge; it never calls `list_contact_windows()`/`reserve_contact()`
itself. Implementing them meaningfully is out of scope until something actually
exercises that path.

## Running it

```bash
docker build -f origo-stellarstation-mock/Dockerfile -t origo-stellarstation-mock:latest .
docker run -d --name origo-stellarstation-sn-002 --network origo-net -p 0:8080 \
  origo-stellarstation-mock:latest
```

Started automatically by `origo-edge`'s `DeviceProvisioner` on Origo Terrestrial
registration — see `docs/docker-device-loop.md`. For iterating on this container
directly without going through origo-edge, `scripts/provision-device-pair.sh` is the
tool that was actually used to find and fix every bug in this file.

## Known limitations

- **The `frames()` dual-mode heuristic is real, not cosmetic.** A station-agent
  container can't run a fresh `KEY_EXCHANGE` during a pass where `DATA_DELIVERY`
  payload happens to be staged on the same Origo Space container — the heuristic
  will drain the staged data instead. Fixing this for real needs a job-type hint
  threaded through `open_link()`/`pass_executor.py`, deliberately not done blind.
- **No test suite of its own.** Everything here was validated by running the real
  device loop repeatedly during development (see the debugging journal), never by
  an automated test exercising `OpenSatelliteStream` directly.
- Booking/discovery RPCs are stubs, as noted above — not a gap in *this* system's
  demo, but a real gap if anything ever needs them.