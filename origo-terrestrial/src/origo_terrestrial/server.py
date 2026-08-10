from __future__ import annotations

import asyncio
import os
from pathlib import Path

import grpc
import uvicorn
from fastapi import FastAPI

from origo_crypto.wolfcrypt_engine import WolfCryptEngine

from ._proto.origo.v1 import origo_pb2_grpc as pb_grpc
from .identity import IdentityStore
from .service import OrigoTerrestrialServicer

SOCKET_PATH = os.environ.get("ORIGO_TERRESTRIAL_SOCKET", "/var/run/origo/origo-terrestrial.sock")

# design §6: "If Origo Terrestrial ever moves to a physically separate board within
# the same enclosure, this reverts to secure_channel — a one-line change, because
# OrigoTerrestrial is a Protocol." Separate Docker containers are exactly that case
# (no shared filesystem for a Unix socket), so: if ORIGO_TERRESTRIAL_GRPC_ADDR is set,
# bind TCP there instead of the Unix socket. Still insecure_port (no TLS) — the
# "insecure" label is about transport encryption, not app-layer trust; see §6's own
# note about that distinction. A real cross-board deployment should add TLS here,
# not just flip the socket type.
GRPC_ADDR = os.environ.get("ORIGO_TERRESTRIAL_GRPC_ADDR")

DEVICE_ID = os.environ.get("ORIGO_TERRESTRIAL_DEVICE_ID", "unknown")
IDENTITY_PATH = Path(os.environ.get("ORIGO_TERRESTRIAL_IDENTITY_PATH", "terrestrial-identity.json"))
HTTP_PORT = int(os.environ.get("ORIGO_TERRESTRIAL_HTTP_PORT", "8080"))


def _load_peer_public_key() -> bytes:
    """Provisioning ceremony, automated for the Docker device loop: prefer a direct
    hex value (what origo-edge's DeviceProvisioner passes, since it already has the
    paired Origo Space device's key in memory and there's no shared filesystem
    between containers to drop a file into) and fall back to the original file path
    for same-host dev, unchanged from before."""
    hex_value = os.environ.get("ORIGO_SPACE_PUBLIC_KEY_HEX")
    if hex_value:
        return bytes.fromhex(hex_value)
    return bytes.fromhex(Path(os.environ["ORIGO_SPACE_PUBLIC_KEY_FILE"]).read_text().strip())


def _build_http_app(identity: IdentityStore) -> FastAPI:
    """Identity-only sidecar — everything crypto-operational stays on the gRPC
    surface. Exists purely so the provisioner (and a human with curl) can read this
    device's own public key without speaking gRPC."""
    app = FastAPI(title="Origo Terrestrial identity sidecar")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "device_id": DEVICE_ID}

    @app.get("/identity")
    def get_identity() -> dict[str, str]:
        return {"device_id": DEVICE_ID, "public_key_hex": identity.public_key.hex()}

    return app


async def _serve_grpc(engine: WolfCryptEngine, identity: IdentityStore, peer_public_key: bytes) -> None:
    server = grpc.aio.server()
    pb_grpc.add_OrigoTerrestrialServiceServicer_to_server(
        OrigoTerrestrialServicer(engine=engine, identity=identity, peer_public_key=peer_public_key), server,
    )
    if GRPC_ADDR:
        server.add_insecure_port(GRPC_ADDR)
        target_desc = GRPC_ADDR
    else:
        server.add_insecure_port(f"unix://{SOCKET_PATH}")   # matches station-agent's default target
        target_desc = SOCKET_PATH
    await server.start()
    print(f"Origo Terrestrial serving on {target_desc}")
    await server.wait_for_termination()


async def _serve_http(identity: IdentityStore) -> None:
    config = uvicorn.Config(_build_http_app(identity), host="0.0.0.0", port=HTTP_PORT, log_level="warning")
    await uvicorn.Server(config).serve()


async def serve() -> None:
    engine = WolfCryptEngine()
    identity = IdentityStore(path=IDENTITY_PATH, engine=engine)
    peer_public_key = _load_peer_public_key()

    await asyncio.gather(
        _serve_grpc(engine, identity, peer_public_key),
        _serve_http(identity),
    )


if __name__ == "__main__":
    asyncio.run(serve())
