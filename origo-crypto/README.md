# `origo-crypto`

The PQC engine both Origo Space and Origo Terrestrial drive: ML-KEM-1024, ML-DSA-87,
AES-256-GCM, and HKDF over wolfCrypt via `ctypes`. A pure library — no network, no
process of its own, no knowledge of which side (satellite or ground) is calling it.
Design reference: [`Origo Design.md`](Origo Design.md) §1, §7.

## Structure

```
origo-crypto/
├── src/origo_crypto/
│   ├── engine.py              # CryptoEngine Protocol — the contract
│   ├── envelope.py            # kem/ct wire framing (KemEnvelope, pack/parse helpers)
│   └── wolfcrypt_engine.py    # WolfCryptEngine — the implementation
└── tests/                     # not written yet — see Known gaps
```

## Why `engine.py` is a Protocol, not a base class

`CryptoEngine` is the full contract — `kem_keygen`/`encapsulate`/`decapsulate`,
`dsa_keygen`/`sign`/`verify`, `aead_encrypt`/`decrypt`, `hkdf`, `random_bytes` — and
`WolfCryptEngine` is the only thing implementing it today. Keeping it a
`typing.Protocol` rather than an ABC means a test double or a future non-wolfSSL
backend doesn't have to inherit from anything, matching the same reasoning
`origo_info_adapter.ports` uses for `GroundNetworkAdapter`.

## `envelope.py` — the wire format, deliberately duplicated

`pack_ek_envelope`/`parse_ek_envelope` and `pack_ct_envelope`/`parse_ct_envelope`
define the byte format both directions of a key exchange travel in. The module's own
docstring is the reason to read before touching it: this same format is specified
independently again in `origo_station_agent.pass_executor`
(`_parse_kem_envelope`/`_frame_ct`) — not imported from here, on purpose. Origo Space
software shouldn't depend on origo-station-agent's package, so the contract is
written out in both places. If you change one, change both.

## `WolfCryptEngine` — what's real, and what had to be found out empirically

Binds directly to `libwolfssl.so` via `ctypes`. Everything it does was verified
against a real running instance, not just written against the header files:

- **ML-KEM-1024**: `wc_MlKemKey_*` — matches the header exactly, no surprises.
- **ML-DSA-87**: signs and verifies via `wc_MlDsaKey_SignCtx`/`VerifyCtx` with an
  empty context (`ctx=NULL, ctxLen=0`) — the plain `wc_MlDsaKey_Sign`/`Verify`
  functions **do not exist** unless wolfSSL was built with `WOLFSSL_MLDSA_NO_CTX`,
  which this build was not. Binding the plain names crashes at import time via a
  `ctypes` `dlsym` failure, not a runtime error — this bit us once already.
- **AES-256-GCM**: one-shot `wc_AesGcmEncrypt`/`Decrypt` only. The streaming API
  (`wc_AesGcmInit`/`EncryptUpdate`/`EncryptFinal`) isn't exported on this build
  (not compiled with `WOLFSSL_AESGCM_STREAM`).
- **HKDF**: `wc_HKDF` with `WC_SHA256 = 6` — **not** the commonly-cited `2`. This
  constant is not portable across wolfSSL builds (FIPS mode, SM3 support, and other
  compile-time flags can shift or alias it), and got this wrong once, producing
  `wc_HKDF failed, rc=-173` (`BAD_FUNC_ARG`). Confirmed empirically, not from a
  header, via:

  ```bash
  python3 - <<'EOF'
  import ctypes
  lib = ctypes.CDLL("libwolfssl.so")
  lib.wc_HmacSizeByType.argtypes = [ctypes.c_int]
  lib.wc_HmacSizeByType.restype = ctypes.c_int
  for name, val in {"MD5":0,"SHA":1,"SHA256":2,"SHA224":8,"SHA384":5,"SHA512":4,"alt3":3,"alt6":6,"alt7":7}.items():
      print(f"{name:8} ({val}): {lib.wc_HmacSizeByType(val)}")
  EOF
  ```

  Whichever candidate prints `32` is the right `WC_SHA256` for a given build. **If
  this code ever runs against a different wolfSSL build, re-run this check before
  trusting `6`.**

- **`Aes`/`WC_RNG` struct sizes**: both are opaque to `ctypes` — only forward-declared
  in the headers, never given a concrete layout. `wolfcrypt_engine.py` allocates
  generous placeholder buffers (256B for `WC_RNG`, 4096B for `Aes`) and says so in a
  comment with the exact `sizeof()` C snippet to run if either one is ever wrong.
  Undersizing either is silent heap corruption, not a clean crash — this was never
  observed to fail, but was also never independently confirmed via `sizeof()`, only
  reasoned about.

## Docker builds: vendor a validated `.so`, don't re-derive `./configure` flags

`origo-space` and `origo-terrestrial`'s Dockerfiles copy a working `/usr/local`
wolfSSL build into the image rather than compiling wolfSSL from source with guessed
flags. The `WC_SHA256=6` finding above is exactly why: that number is a property of
*this specific compiled binary* (its FIPS/SM3/other build-time configuration), and a
fresh `./configure` run — even with the "right" `--enable-mlkem --enable-dilithium
--enable-aesgcm --enable-hkdf` flags — could legitimately produce a different one,
silently reintroducing the same bug inside a container where there's no REPL open to
diagnose it. If you ever do switch to building from source, re-run the
`wc_HmacSizeByType` sweep above against the new binary before trusting anything.

## Known gaps

- **No test suite.** Everything above was validated by direct interactive use and by
  `origo-space/tests/test_server.py`'s roundtrip test (which exercises
  `WolfCryptEngine` in full via `origo_space.server`, but from outside this package).
  A `tests/` directory exercising `WolfCryptEngine` directly — keygen round-trips,
  tamper detection on `dsa_verify`, AEAD tag rejection on a flipped byte — doesn't
  exist yet.
- **`WC_SHA256 = 6` is this build's answer, not a portable constant.** Anyone running
  this against a different wolfSSL binary needs to re-run the diagnostic above.
- Sizes for the opaque `Aes`/`WC_RNG` structs are conservative placeholders, not
  confirmed `sizeof()` values.