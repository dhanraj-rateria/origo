# Build context is the REPO ROOT (docker build -f origo-space/Dockerfile .), so this
# can reach both origo-crypto/ and a vendored wolfSSL build.
#
# ----------------------------------------------------------------------------------
# wolfSSL: vendor your already-validated build rather than re-deriving configure
# flags blind. Before `make images` / `docker build`, run once from the repo root:
#
#   mkdir -p vendor/wolfssl/lib vendor/wolfssl/include
#   cp -a /usr/local/lib/libwolfssl.so* vendor/wolfssl/lib/
#   cp -r /usr/local/include/wolfssl    vendor/wolfssl/include/wolfssl
#
# That's the exact build your `nm -D libwolfssl.so` dump confirmed has ML-KEM-1024,
# ML-DSA-87 (Ctx variants only), AES-GCM (one-shot API only), and HKDF — the same
# feature set origo_crypto.wolfcrypt_engine.py was written against. Re-building from
# source instead is possible (uncomment the alternate stage below) but untested here:
# I don't have a network in this environment to actually compile and confirm the
# configure flags, so treat that path the same way the wolfcrypt_engine.py review
# flagged the Aes/WC_RNG struct sizes — a starting point to verify, not a given.
# ----------------------------------------------------------------------------------

FROM python:3.12-slim AS base

COPY vendor/wolfssl/lib/     /usr/local/lib/
COPY vendor/wolfssl/include/ /usr/local/include/
RUN ldconfig

# --- alternative: build wolfSSL 5.9.2 from source instead of vendoring ------------
# FROM python:3.12-slim AS wolfssl-build
# RUN apt-get update && apt-get install -y --no-install-recommends \
#       build-essential autoconf automake libtool git ca-certificates && \
#     rm -rf /var/lib/apt/lists/*
# RUN git clone --depth 1 --branch v5.9.2 https://github.com/wolfSSL/wolfssl.git /src
# WORKDIR /src
# RUN ./autogen.sh && \
#     ./configure --enable-mlkem --enable-dilithium --enable-aesgcm --enable-hkdf && \
#     make -j"$(nproc)" && make install && ldconfig
# # ...then replace the two COPY lines above with:
# # COPY --from=wolfssl-build /usr/local/lib/libwolfssl.so*   /usr/local/lib/
# # COPY --from=wolfssl-build /usr/local/include/wolfssl      /usr/local/include/wolfssl
# # RUN ldconfig

WORKDIR /app
COPY origo-crypto/ ./origo-crypto/
COPY origo-space/ ./origo-space/
RUN pip install --no-cache-dir ./origo-crypto ./origo-space

ENV ORIGO_SPACE_IDENTITY_PATH=/data/identity.json
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["uvicorn", "origo_space.server:app", "--host", "0.0.0.0", "--port", "8080"]
