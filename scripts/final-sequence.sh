#!/usr/bin/env bash
set -euo pipefail

NET=origo-net

echo "== 1. Origo Space =="
docker rm -f origo-space-sn-001 2>/dev/null || true
docker run -d --name origo-space-sn-001 --network "$NET" -p 0:8080 \
  -e ORIGO_SPACE_DEVICE_ID=SN-001 \
  -v origo-identity-origo-space-sn-001:/data \
  origo-space:latest
sleep 2
SPACE_PORT=$(docker port origo-space-sn-001 8080/tcp | cut -d: -f2)
echo "space port: $SPACE_PORT"
until curl -sf "http://localhost:$SPACE_PORT/health" >/dev/null; do sleep 1; done

echo "== 2. StellarStation mock =="
docker rm -f origo-stellarstation-sn-002 2>/dev/null || true
docker run -d --name origo-stellarstation-sn-002 --network "$NET" -p 0:8080 \
  origo-stellarstation-mock:latest
sleep 2
SS_PORT=$(docker port origo-stellarstation-sn-002 8080/tcp | cut -d: -f2)
echo "stellarstation admin port: $SS_PORT"
until curl -sf "http://localhost:$SS_PORT/health" >/dev/null; do sleep 1; done

echo "== 3. Register the satellite mapping =="
curl -sf -X POST "http://localhost:$SS_PORT/admin/satellites/SN-001" \
  -H 'content-type: application/json' -d '{"space_url":"http://origo-space-sn-001:8080"}' >/dev/null

echo "== 4. Fetch Space's public key (relayed through the mock, not direct) =="
SPACE_PUBKEY=$(curl -sf "http://localhost:$SS_PORT/admin/satellites/SN-001/identity" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['public_key_hex'])")
echo "space pubkey: ${SPACE_PUBKEY:0:20}...(${#SPACE_PUBKEY} chars)"

echo "== 5. Origo Terrestrial — space pubkey baked in at creation =="
docker rm -f origo-terrestrial-sn-002 2>/dev/null || true
docker run -d --name origo-terrestrial-sn-002 --network "$NET" -p 0:8080 \
  -e ORIGO_TERRESTRIAL_DEVICE_ID=SN-002 \
  -e ORIGO_TERRESTRIAL_GRPC_ADDR=0.0.0.0:50051 \
  -e ORIGO_SPACE_PUBLIC_KEY_HEX="$SPACE_PUBKEY" \
  -v origo-identity-origo-terrestrial-sn-002:/data \
  origo-terrestrial:latest
sleep 2
TERR_PORT=$(docker port origo-terrestrial-sn-002 8080/tcp | cut -d: -f2)
echo "terrestrial port: $TERR_PORT"
until curl -sf "http://localhost:$TERR_PORT/health" >/dev/null; do sleep 1; done

echo "== 6. Push Terrestrial's pubkey to Space, relayed through the mock =="
TERR_PUBKEY=$(curl -sf "http://localhost:$TERR_PORT/identity" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['public_key_hex'])")
curl -sf -X POST "http://localhost:$SS_PORT/admin/satellites/SN-001/peer" \
  -H 'content-type: application/json' -d "{\"public_key_hex\":\"$TERR_PUBKEY\"}" >/dev/null
echo "provisioning ceremony complete"

echo "== 7. Origo Station Agent — last, now that everything it needs exists =="
docker rm -f origo-station-agent-sn-002 2>/dev/null || true
docker run -d --name origo-station-agent-sn-002 --network "$NET" \
  -e ORIGO_STATION_STATION_REF=SN-002 \
  -e ORIGO_STATION_SATELLITE_REF=SN-001 \
  -e ORIGO_STATION_ORIGO_EDGE_URL=http://host.docker.internal:8000 \
  -e ORIGO_STATION_ORIGO_ENDPOINT=origo-terrestrial-sn-002:50051 \
  -e ORIGO_STELLARSTATION_ENABLED=true \
  -e ORIGO_STELLARSTATION_ENDPOINT=origo-stellarstation-sn-002:50052 \
  --add-host=host.docker.internal:host-gateway \
  origo-station-agent:latest

echo "== done =="
docker ps --filter "name=sn-00" --format "table {{.Names}}\t{{.Status}}"