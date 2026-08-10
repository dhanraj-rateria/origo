# Build context is the REPO ROOT (docker build -f origo-terrestrial/Dockerfile .).
# Same wolfSSL vendoring note as origo-space/Dockerfile — see that file for the
# full explanation and the from-source alternative.
#
#   mkdir -p vendor/wolfssl/lib vendor/wolfssl/include
#   cp -a /usr/local/lib/libwolfssl.so* vendor/wolfssl/lib/
#   cp -r /usr/local/include/wolfssl    vendor/wolfssl/include/wolfssl

FROM python:3.12-slim AS base

COPY vendor/wolfssl/lib/     /usr/local/lib/
COPY vendor/wolfssl/include/ /usr/local/include/
RUN ldconfig

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY origo-crypto/ ./origo-crypto/
COPY origo-terrestrial/ ./origo-terrestrial/

RUN pip install --no-cache-dir grpcio-tools>=1.66 && \
    python origo-terrestrial/scripts/gen_proto.py && \
    pip install --no-cache-dir ./origo-crypto ./origo-terrestrial

ENV ORIGO_TERRESTRIAL_IDENTITY_PATH=/data/identity.json
ENV ORIGO_TERRESTRIAL_SOCKET=/var/run/origo/origo-terrestrial.sock
VOLUME ["/data"]
EXPOSE 50051 8080

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "origo_terrestrial.server"]
