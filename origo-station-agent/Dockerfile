# Build context is the REPO ROOT (docker build -f origo-station-agent/Dockerfile .).
# No wolfCrypt/wolfSSL here — this process does no cryptography (design §1/§7), so
# unlike origo-space and origo-terrestrial's Dockerfiles, this is a plain image.

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends build-essential openssl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY origo-info-adapter/ ./origo-info-adapter/
COPY origo-station-agent/ ./origo-station-agent/

RUN pip install --no-cache-dir grpcio-tools>=1.66 && \
    python origo-station-agent/scripts/gen_proto.py && \
    pip install --no-cache-dir ./origo-info-adapter ./origo-station-agent

# Placeholder mTLS identity. SyncClient's httpx.AsyncClient loads these into an
# SSLContext eagerly at construction time regardless of whether origo-edge ends up
# being plain HTTP or HTTPS (see .env.example's note) — ORIGO_AUTH_DISABLED on the
# edge side is what actually lets dev traffic through unauthenticated; these files
# only need to exist and parse as valid PEM, they don't need to be trusted by
# anything. Not for anything but local dev — see docs/docker-device-loop.md.
RUN mkdir -p /certs && \
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
      -keyout /certs/dev.key -out /certs/dev.crt -subj "/CN=origo-station-agent-dev" && \
    cp /certs/dev.crt /certs/ca.pem

ENV ORIGO_STATION_DEVICE_CERT_PATH=/certs/dev.crt
ENV ORIGO_STATION_DEVICE_KEY_PATH=/certs/dev.key
ENV ORIGO_STATION_CA_BUNDLE_PATH=/certs/ca.pem

CMD ["python", "-m", "origo_station_agent.main"]
