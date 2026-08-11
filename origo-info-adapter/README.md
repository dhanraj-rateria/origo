# `origo-info-adapter`

A pure library wrapping ground-network providers behind a provider-neutral
`GroundNetworkAdapter` interface. Imported directly into `origo-station-agent`'s
process for the real StellarStation/fake paths — no separate deployment, no network
hop of its own kind. The Docker device-loop path (`dockerlink/`) is the one exception:
it does make its own HTTP calls, standing in for RF/StellarStation entirely, not
wrapping a real provider. Design reference: [`PQC-HSM-Design.md`](PQC-HSM-Design.md)
§3, §6.

## Structure

```
origo-info-adapter/
├── proto/
│   ├── UPSTREAM.txt                        # source repo + tag + retrieval date
│   └── stellarstation/api/v1/              # vendored from infostellarinc/stellarstation-api
├── scripts/gen_proto.py
├── src/origo_info_adapter/
│   ├── models.py                           # provider-neutral domain types
│   ├── ports.py                            # GroundNetworkAdapter + ContactLink
│   ├── errors.py, retry.py, clock.py
│   ├── _grpc_errors.py                     # gRPC status -> adapter error translation
│   ├── stellarstation/
│   │   ├── config.py, channel.py, mapping.py, adapter.py, link.py
│   ├── fake/adapter.py                     # InMemoryAdapter
│   └── dockerlink/adapter.py               # DockerLinkAdapter — Docker device-loop mock
└── tests/
    ├── fake_grpc/servicer.py               # in-process fake StellarStationService
    ├── test_adapter_reserve.py, test_mapping.py
    ├── test_integration.py                 # real StellarStation, credential-gated
    └── dockerlink/test_adapter.py
```

## Why this exists as its own package

Every ground-network provider (StellarStation today; KSAT, Leaf Space, others later)
has its own API shape. `GroundNetworkAdapter` (`ports.py`) is what the rest of the
system depends on — `pass_executor.py` calls `open_link()`, `frames()`,
`send_commands()`, never anything StellarStation-specific. Adding a second provider is
a new module under `origo_info_adapter/`, not a change anywhere else — `dockerlink/`
is proof of exactly that: an entirely different backend (a container over HTTP
instead of a real ground station over gRPC) with zero changes to `pass_executor.py`.

## `build_adapter()` — the factory, and why it checks Docker first

```python
def build_adapter() -> GroundNetworkAdapter:
    if os.environ.get("ORIGO_RF_LINK_URL"):
        return DockerLinkAdapter(base_url=...)      # Docker device loop
    settings = StellarStationSettings()             # validates real credentials
    if not settings.enabled:
        return InMemoryAdapter()                    # unit tests
    return StellarStationAdapter(settings)           # production
```

`ORIGO_RF_LINK_URL` is checked unconditionally, before `StellarStationSettings()` is
even constructed — a station-agent container provisioned for the Docker device loop
has no StellarStation credentials to validate, and shouldn't need any.

## `dockerlink/adapter.py` — mocking RF/StellarStation with a real HTTP hop

`DockerLinkAdapter`/`DockerLink` don't wrap a real provider at all — they talk
directly to an `origo_space.server` container over the Docker network. This is the
mocked half of the Docker device loop: no S-band physics, no orbit geometry, no
Infostellar API call anywhere in this file — a "pass" is simply "call the satellite
container's HTTP endpoint right now." Real bytes still cross a real container
boundary; only the RF/booking layer is fake.

**`frames()` is dual-mode**, decided fresh on every call: it asks Origo Space whether
anything's staged (`GET /downlink/data/status`) — if so, this pass drains it as a
`DATA_DELIVERY` pass; if not, it falls back to `POST /downlink/trigger`
(`KEY_EXCHANGE`). This is a heuristic, not a real job-type signal — `ContactLink`'s
`frames()` takes no arguments by design ("opaque bytes in, opaque bytes out"), and
`pass_executor.py`'s `_run_step` doesn't pass one either, so there's genuinely no
clean way for `DockerLink` to know which job it's serving. The heuristic holds for
how the demo is actually operated (complete a key exchange, *then* stage and deliver
data — never both in the same pass) but it's a real limitation, not a general
solution: **a station-agent container can't run a fresh key exchange during a pass
where data happens to be staged.** Fixing that for real means threading a job-type
hint through `open_link()` and `pass_executor.run()` — deliberately not done without
that file's own test coverage backing the change.

`DownlinkFrame.data` for a data-delivery frame is **raw ciphertext**, no envelope
wrapper — see `origo-space.md` for why (short version: `_run_data_delivery` tracks
its own sequence number and would fail to authenticate anything with extra bytes
glued on).

Booking/discovery methods (`list_contact_windows`, `reserve_contact`,
`cancel_contact`) raise `NotImplementedError` rather than pretending to support a
model that doesn't exist for a direct container link — `list_contacts` and the
ephemeris methods return empty/`None` since `main.py`/`pass_executor.py` never
actually call them in this flow.

## The provider-neutral model, and why the reservation token is handled the way it is

`models.py` defines `ContactWindow`, `ContactOption`, `Contact` etc. — nothing here is
a protobuf message, and `Band` is *derived* from frequency rather than read off the
wire (StellarStation gives Hz, not a band label). `ContactOption.reservation_token` is
excluded from `repr()` and `model_dump()` — it's a single-use bearer credential that
books billable antenna time, and making it structurally impossible to log or leak
beats a comment saying not to.

## Why `reserve_contact` never retries

A reservation token is single-use. If the RPC times out *after* the server actually
booked the pass, retrying either double-books or fails with `FAILED_PRECONDITION` and
there's no way to tell which happened from the client side. `retry.py`'s `NO_RETRY`
policy is used specifically here; the correct recovery is reconciliation
(`list_contacts()` against what the provider actually has), never resending the token.
Every other read (`list_contact_windows`, `list_contacts`) uses the default retry
policy, since reads are safe to repeat.

## Getting the real protos (if `proto/stellarstation/` is empty)

```bash
git clone --depth 1 --branch <latest-release-tag> \
  https://github.com/infostellarinc/stellarstation-api.git /tmp/ss-api
mkdir -p proto/stellarstation
cp -r /tmp/ss-api/api/src/main/proto/stellarstation/. proto/stellarstation/
rm -rf /tmp/ss-api
```

Pin to a tagged release, not the default branch — check the repo's release tags for
the current one. Then `make proto` (from repo root) to generate stubs.

## Credentials and testing, in order

Four stages — don't skip past the first without a reason:

1. **Fake, no credentials.** Default (`ORIGO_STELLARSTATION_ENABLED` unset). `make
   test` runs against `fake/adapter.py`'s `InMemoryAdapter`.
2. **Docker mock, no credentials, real containers.** `ORIGO_RF_LINK_URL` set — the
   device-loop path, real bytes over a real container-to-container HTTP hop, still no
   real ground-network provider involved. See `docs/docker-device-loop.md`.
3. **QA, real but non-billable.** Register on the StellarStation Console, download a
   service-account key, point at `stream.qa.stellarstation.com:443`. `make test-int`.
4. **Production**, only once 1–3 pass — `api.stellarstation.com:443`, a *separate*
   credential from the QA one so a QA key left configured can't book real antenna time.

```bash
export ORIGO_STELLARSTATION_ENABLED=true
export ORIGO_STELLARSTATION_API_KEY_PATH=/secure/path/to/key.json
export ORIGO_STELLARSTATION_ENDPOINT=stream.qa.stellarstation.com:443
export ORIGO_STELLARSTATION_AUDIENCE=https://stream.qa.stellarstation.com
```

If this fails `UNAUTHENTICATED`, check `ORIGO_STELLARSTATION_AUDIENCE` first — it isn't
always the same string as the endpoint, and that mismatch is the most common first-run
failure (see `config.py`'s own comment on the field).

## Tests

```bash
uv run pytest tests/ -m "not integration" -v      # fake gRPC server, no credentials
uv run pytest tests/ -m integration -v            # real StellarStation, QA credentials
uv run pytest tests/dockerlink -v                 # respx-mocked, no containers, no credentials
```

| File | Proves |
|---|---|
| `test_adapter_reserve.py` | Successful reserve; `FAILED_PRECONDITION` → `ReservationTokenRejected`; a reused token rejected; `UNAVAILABLE` on reserve makes exactly one server call (proves `NO_RETRY`); `UNAVAILABLE` on a read *does* retry and succeeds |
| `test_mapping.py` | Unset `Timestamp` → `None`, not epoch 1970; band derivation at real S/X-band frequencies; `(0,0)` coordinates → `None`, not a real station; the reservation-token leak test — `model_dump()` never contains it |
| `test_integration.py` | The real StellarStation client actually connects and lists windows — credential-gated, deselected by default |
| `dockerlink/test_adapter.py` | Both `frames()` modes (data-drain vs. key-exchange fallback, including the fallback triggering on a broken status check, not just an empty queue); `send_commands` success/failure; the deliberately-`NotImplementedError` booking surface |

`tests/fake_grpc/servicer.py` is the highest-value test asset for the StellarStation
path — an in-process gRPC server implementing the real `StellarStationService`
interface, giving real gRPC semantics (status codes, streaming) with zero network and
zero credentials. `dockerlink/test_adapter.py` plays the equivalent role for the
Docker device-loop path, using `respx` instead of a fake gRPC server since that path
is HTTP, not gRPC.

## Known gaps

- Only `ReservePass`/`ListPlans`/`CancelPlan`/`ListUpcomingAvailablePasses` are covered
  by `fake_grpc/servicer.py` — `AddTle`/`GetTle`/`SetTleSource`/`SetPlanMetadata` calls
  in `adapter.py` don't have fake-server coverage yet.
- `link.py`'s bidirectional streaming (`OpenSatelliteStream`) has no dedicated test
  beyond what `origo-station-agent`'s `InMemoryAdapter`-based tests exercise indirectly.
- **`DockerLinkAdapter`'s `frames()` heuristic is a real limitation, not just an
  implementation detail** — see the `dockerlink/adapter.py` section above. A correct
  general fix needs a job-type hint threaded through `ContactLink`/`pass_executor.py`,
  which hasn't been done.
- `DockerLinkAdapter` only implements the `KEY_EXCHANGE`/`DATA_DELIVERY` hops used by
  the current demo — `CONFIG_PUSH` isn't wired through it (`apply_config` goes
  straight from `pass_executor.py` to Origo Terrestrial's gRPC service, no adapter
  involvement either way, so this isn't actually a gap for that job type specifically
  — noted here only so it's not assumed missing by omission).