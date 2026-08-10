from __future__ import annotations

import asyncio
import os
from pathlib import Path

import grpc

from origo_crypto.wolfcrypt_engine import WolfCryptEngine

from ._proto.origo.v1 import origo_pb2_grpc as pb_grpc
from .identity import IdentityStore
from .service import OrigoTerrestrialServicer

SOCKET_PATH = os.environ.get("ORIGO_TERRESTRIAL_SOCKET", "/var/run/origo/origo-terrestrial.sock")


async def serve() -> None:
    engine = WolfCryptEngine()
    identity = IdentityStore(path=Path("terrestrial-identity.json"), engine=engine)
    peer_public_key = bytes.fromhex(Path(os.environ["ORIGO_SPACE_PUBLIC_KEY_FILE"]).read_text().strip())

    server = grpc.aio.server()
    pb_grpc.add_OrigoTerrestrialServiceServicer_to_server(
        OrigoTerrestrialServicer(engine=engine, identity=identity, peer_public_key=peer_public_key), server,
    )
    server.add_insecure_port(f"unix://{SOCKET_PATH}")   # matches station-agent's default target
    await server.start()
    print(f"Origo Terrestrial serving on {SOCKET_PATH}")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())