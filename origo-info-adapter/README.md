# `origo-info-adapter`

A pure library wrapping the Infostellar StellarStation API behind a provider-neutral
`GroundNetworkAdapter` interface. Imported directly into `origo-station-agent`'s
process — no separate deployment, no network hop of its own kind. Design reference:
[`PQC-HSM-Design.md`](PQC-HSM-Design.md) §3, §6.

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
│   └── fake/adapter.py                     # InMemoryAdapter
└── tests/
    ├── fake_grpc/servicer.py               # in-process fake StellarStationService
    ├── test_adapter_reserve.py, test_mapping.py
    └── test_integration.py                 # real StellarStation, credential-gated
```

## Why this exists as its own package

Every ground-network provider (StellarStation today; KSAT, Leaf Space, others later)
has its own API shape. `GroundNetworkAdapter` (`ports.py`) is what the rest of the
system depends on — `pass_executor.py` calls `open_link()`, `frames()`,
`send_commands()`, never anything StellarStation-specific. Adding a second provider is
a new module under `origo_info_adapter/`, not a change anywhere else.

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

Three stages — don't skip to the last one:

1. **Fake, no credentials.** Default (`ORIGO_STELLARSTATION_ENABLED` unset). `make
   test` runs against `fake/adapter.py`'s `InMemoryAdapter`.
2. **QA, real but non-billable.** Register on the StellarStation Console, download a
   service-account key, point at `stream.qa.stellarstation.com:443`. `make test-int`.
3. **Production**, only once 1 and 2 pass — `api.stellarstation.com:443`, a *separate*
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
```

| File | Proves |
|---|---|
| `test_adapter_reserve.py` | Successful reserve; `FAILED_PRECONDITION` → `ReservationTokenRejected`; a reused token rejected; `UNAVAILABLE` on reserve makes exactly one server call (proves `NO_RETRY`); `UNAVAILABLE` on a read *does* retry and succeeds |
| `test_mapping.py` | Unset `Timestamp` → `None`, not epoch 1970; band derivation at real S/X-band frequencies; `(0,0)` coordinates → `None`, not a real station; the reservation-token leak test — `model_dump()` never contains it |
| `test_integration.py` | The real StellarStation client actually connects and lists windows — credential-gated, deselected by default |

`tests/fake_grpc/servicer.py` is the highest-value test asset here: an in-process gRPC
server implementing the real `StellarStationService` interface, giving real gRPC
semantics (status codes, streaming) with zero network and zero credentials for every
other test in the suite.

## Known gaps

- Only `ReservePass`/`ListPlans`/`CancelPlan`/`ListUpcomingAvailablePasses` are covered
  by `fake_grpc/servicer.py` — `AddTle`/`GetTle`/`SetTleSource`/`SetPlanMetadata` calls
  in `adapter.py` don't have fake-server coverage yet.
- `link.py`'s bidirectional streaming (`OpenSatelliteStream`) has no dedicated test
  beyond what `origo-station-agent`'s `InMemoryAdapter`-based tests exercise indirectly.