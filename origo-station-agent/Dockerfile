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

# Placeholder mTLS identity for the origo-edge link. SyncClient's httpx.AsyncClient
# loads these into an SSLContext eagerly at construction time regardless of whether
# origo-edge ends up being plain HTTP or HTTPS (see .env.example's note) —
# ORIGO_AUTH_DISABLED on the edge side is what actually lets dev traffic through
# unauthenticated; these files only need to exist and parse as valid PEM. Not for
# anything but local dev — see docs/docker-device-loop.md.
RUN mkdir -p /certs && \
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
      -keyout /certs/dev.key -out /certs/dev.crt -subj "/CN=origo-station-agent-dev" && \
    cp /certs/dev.crt /certs/ca.pem

ENV ORIGO_STATION_DEVICE_CERT_PATH=/certs/dev.crt
ENV ORIGO_STATION_DEVICE_KEY_PATH=/certs/dev.key
ENV ORIGO_STATION_CA_BUNDLE_PATH=/certs/ca.pem

# Real StellarStation link: a fake-but-real-RSA-keyed Google service-account JSON
# (google_auth_jwt.Credentials.from_service_account_file() genuinely parses and
# signs with this key — real crypto, not a placeholder string — it just never
# leaves this container, and origo-stellarstation-mock's gRPC server accepts the
# connection on TLS alone without verifying the JWT) plus that mock's shared,
# static, self-signed CA (same file baked into origo-stellarstation-mock's own
# image — see that Dockerfile's comment on why it's static and what the
# server-name override is for).
COPY origo-stellarstation-mock/certs/fake-service-account.json /certs/stellarstation-key.json
COPY origo-stellarstation-mock/certs/server.crt /certs/stellarstation-ca.pem

ENV ORIGO_STELLARSTATION_API_KEY_PATH=/certs/stellarstation-key.json
ENV ORIGO_STELLARSTATION_CA_BUNDLE_PATH=/certs/stellarstation-ca.pem
ENV ORIGO_STELLARSTATION_TLS_SERVER_NAME_OVERRIDE=origo-stellarstation-mock
ENV ORIGO_STELLARSTATION_AUDIENCE=https://origo-stellarstation-mock.local
ENV ORIGO_STELLARSTATION_INSECURE=false
# ORIGO_STELLARSTATION_ENABLED and ORIGO_STELLARSTATION_ENDPOINT are deployment-
# specific (which mock instance this station-agent pairs with) — set by
# DeviceProvisioner at container-creation time, same as ORIGO_STATION_STATION_REF
# etc. already are, not baked in here.

CMD ["python", "-m", "origo_station_agent.main"]
