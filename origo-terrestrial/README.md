# `origo-terrestrial`

The ground-side Origo module - a **software stand-in** for the hardware/firmware module, 
co-located with `origo-station-agent` on the same physical hardware in the
design. Design reference: [`Origo Design.md`](Origo Design.md) §1, §5.2, §7.

## Structure

```
origo-terrestrial/
├── Dockerfile                       # vendors a validated wolfSSL build - see origo-crypto.md
├── proto/origo/v1/origo.proto       # server-side copy - see "the proto, duplicated" below
├── scripts/gen_proto.py             # generates this package's own _proto stubs
└── src/origo_terrestrial/
    ├── identity.py                  # IdentityStore - this device's own keypair
    ├── service.py                   # OrigoTerrestrialServicer - implements the gRPC service
    └── server.py                    # gRPC server + a small HTTP identity sidecar
```

## The proto, duplicated on purpose

`origo-station-agent/proto/origo/v1/origo.proto` and this package's own copy define
the identical `OrigoTerrestrialService` contract - one generates the *client* stub
(`GrpcOrigoTerrestrial`), the other the *server* stub
(`OrigoTerrestrialServiceServicer`, which `service.py` subclasses). Duplicated, not
imported from one side to the other, the two sides are separate deployable units and shouldn't
depend on each other's package. If either `.proto` changes, both must change
together - there is no tooling enforcing that today.

```bash
python scripts/gen_proto.py    # regenerates src/origo_terrestrial/_proto
```

`gen_proto.py` post-processes the generated `*_pb2_grpc.py` to rewrite `protoc`'s
absolute sibling import (`from origo.v1 import origo_pb2 as ...`) into a relative one
(`from . import origo_pb2 as ...`). This isn't optional cleanup - the absolute form
raises `ModuleNotFoundError: No module named 'origo'` the moment anything tries to
import the generated grpc stub, since there's no real top-level `origo` package on
`sys.path`. It's a well-documented `grpc_tools.protoc` behavior for nested output
directories, not specific to this repo - but it bit this exact package once, so it's
worth knowing the fix lives in the generation script now, not as a one-off manual
`sed`.

## `service.py` - `OrigoTerrestrialServicer`

- **`VerifyAndEncapsulate`**: verifies the satellite's ML-DSA-87 signature over
  `ek + device_id + nonce`, checks nonce freshness against a rolling
  `NONCE_FRESHNESS_WINDOW_SEC = 120` window (rejecting replays), then
  ML-KEM-1024-Encapsulates, derives the traffic key via `wc_HKDF` with
  `context=b"origo-traffic-key"`, and signs the resulting `ct`. The traffic key is
  kept in `self._active_keys`, keyed by a locally-generated `key-<hex>` id - never
  returned to the caller, never written anywhere outside this process's memory.
- **`DecryptPayload`**: looks up the traffic key by `key_id`, derives the nonce
  directly from `sequence_number` (`.to_bytes(12, "big")` - the caller's own
  monotonic counter, not anything read from the ciphertext), and AEAD-decrypts.
- **`ApplyConfig`**: **placeholder.** `self._engine.dsa_verify(..., signature=b"")` -
  an empty signature - will always fail, and the result is silently discarded either
  way (`if not verify: pass`). This RPC currently does nothing beyond accepting the
  call and returning an empty response; there's no policy concept yet for it to apply,
  and no real signature to check until one exists. Not something this session
  addressed - flagged here so it doesn't quietly look finished.

## `server.py` - gRPC + a small HTTP identity sidecar

Binds the gRPC service to a Unix domain socket by default
(`ORIGO_TERRESTRIAL_SOCKET`, matching "same physical hardware" in the design) - or to
TCP if `ORIGO_TERRESTRIAL_GRPC_ADDR` is set (e.g. `0.0.0.0:50051`), which is what the
Docker device loop uses, since separate containers have no shared filesystem for a
Unix socket to live on. Design §6 explicitly sanctions this swap ("a one-line change,
because `OrigoTerrestrial` is a `Protocol`") - still `add_insecure_port` either way;
switching socket types doesn't add TLS, and a real cross-board deployment would need
to.

Runs a second, tiny FastAPI app alongside the gRPC server (`asyncio.gather`) exposing
`GET /health` and `GET /identity` - identity-only, no crypto operations. Exists
purely so the Docker device-loop provisioner (or a human with `curl`) can read this
device's own public key without speaking gRPC; every actual crypto operation stays on
the gRPC surface.

The peer (Origo Space) public key can come from either `ORIGO_SPACE_PUBLIC_KEY_FILE`
(a path - the original, same-host mechanism) or `ORIGO_SPACE_PUBLIC_KEY_HEX` (a
direct value - what the Docker provisioner sets, since there's no shared filesystem
between containers to drop a file into).

## Running it

```bash
python scripts/gen_proto.py
uv run python -m origo_terrestrial.server
```

Env vars: `ORIGO_TERRESTRIAL_DEVICE_ID`, `ORIGO_TERRESTRIAL_IDENTITY_PATH`,
`ORIGO_TERRESTRIAL_SOCKET` / `ORIGO_TERRESTRIAL_GRPC_ADDR`,
`ORIGO_SPACE_PUBLIC_KEY_FILE` / `ORIGO_SPACE_PUBLIC_KEY_HEX`,
`ORIGO_TERRESTRIAL_HTTP_PORT` (default `8080`).

Via the Docker device loop, started automatically by `origo-edge`'s
`DeviceProvisioner` on `POST /v1/devices` with `type=ORIGO_TERRESTRIAL` - see
`docs/docker-device-loop.md`.

## Known gaps

- **`ApplyConfig` is a placeholder** - see above. Verifies nothing real, applies
  nothing, because there's no signed config payload or policy model yet.
- **No test suite of its own.** `service.py`'s real behavior is exercised indirectly
  - by `tests/test_end_to_end_key_exchange.py` at the repo root (real handshake, one
  in-process gRPC server) and by the live Docker device-loop run - but nothing tests
  `OrigoTerrestrialServicer` in isolation (nonce replay rejection, a tampered
  signature, a `DecryptPayload` call for an unknown `key_id`).
- **Nonce freshness window (120s) is a fixed constant**, not configurable, and
  `_seen_nonces` is an in-memory dict cleared on restart - a real HSM would need
  durable replay protection across restarts.
- Same wolfSSL vendoring caveat as `origo-crypto.md` - the Docker image ships
  whatever `.so` you copy into `vendor/wolfssl/`, not a from-source build with
  verified flags.