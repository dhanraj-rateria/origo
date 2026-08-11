# Build context is the REPO ROOT (docker build -f origo-stellarstation-mock/Dockerfile .).
# Depends on origo-info-adapter purely to reuse its generated stellarstation.proto
# Python stubs (origo_info_adapter._proto.stellarstation...) — not its adapter logic.
# Needs the real protos vendored under origo-info-adapter/proto/stellarstation/ first
# (see that package's own README if that directory is empty).

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY origo-info-adapter/ ./origo-info-adapter/
COPY origo-stellarstation-mock/ ./origo-stellarstation-mock/

RUN pip install --no-cache-dir grpcio-tools>=1.66 && \
    python origo-info-adapter/scripts/gen_proto.py && \
    pip install --no-cache-dir ./origo-info-adapter ./origo-stellarstation-mock

# Static, shared, self-signed cert — not a secret, doesn't protect anything real.
# CN/SAN is the fixed symbolic name "origo-stellarstation-mock", not tied to any
# real container hostname (those vary per deployment: origo-stellarstation-sn-002,
# -sn-005, ...). origo-station-agent's channel is configured with
# ORIGO_STELLARSTATION_TLS_SERVER_NAME_OVERRIDE=origo-stellarstation-mock to match
# regardless of which actual hostname it dials — see that Dockerfile, which bakes in
# this exact same cert as its trusted CA.
COPY origo-stellarstation-mock/certs/server.crt /certs/server.crt
COPY origo-stellarstation-mock/certs/server.key /certs/server.key

EXPOSE 50052 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=2).status==200 else 1)"

CMD ["python", "-m", "origo_stellarstation_mock.server"]
