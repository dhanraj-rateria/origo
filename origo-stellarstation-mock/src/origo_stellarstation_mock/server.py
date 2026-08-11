"""A protocol-accurate StellarStation emulator: implements the real
stellarstation.proto OpenSatelliteStream RPC against a real generated gRPC stub,
relaying to whichever Origo Space container is registered for a given satellite_id.

This replaces origo_info_adapter.dockerlink.DockerLinkAdapter's custom REST shape —
origo-station-agent now runs the real, unmodified StellarStationAdapter/
StellarStationLink client code (from origo-info-adapter) against this server instead
of against Infostellar's real cloud API. Nothing in origo_info_adapter or
origo_station_agent changes to make that swap; it's entirely a matter of which
ORIGO_STELLARSTATION_* env vars origo-edge's DeviceProvisioner sets when it creates a
station-agent container.

*** THE SINGLE LEAST-TESTED FILE IN THIS WHOLE SYSTEM ***
OpenSatelliteStream is a hand-built bidirectional gRPC stream implementation, written
against the real stellarstation.proto contract, in an environment with no grpc
runtime available to actually exercise it. Every message shape below (SatelliteStream
Request/Response, Telemetry, StreamEvent, CommandSentFromGroundStation) was checked
field-by-field against the real .proto — that part is solid. What ISN'T verified: that
grpc.aio's ServicerContext.read()/write() pattern (used here instead of the simpler
request-in/response-out async-generator style, because StellarStationLink.frames()
needs to receive a downlink frame *without* the client having sent anything since the
setup message — a strict generator can't do that) behaves exactly as expected end to
end. Run the real loop against this before trusting anything built on top of it.

Also NOT implemented: the booking/discovery RPCs (ListPlans, ReservePass, CancelPlan,
ListUpcomingAvailablePasses, AddTle, GetTle, SetTleSource, SetPlanMetadata). Nothing in
this system's actual runtime path calls them — PassExecutor.run() is handed a JobPlan
directly by origo-edge; it never calls list_contact_windows()/reserve_contact() itself.
They're stubbed only so a real StellarStationAdapter call against them doesn't crash
this process outright, not because they're load-bearing for the demo.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import grpc
import httpx
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import BaseModel

from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2 as ss
from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2_grpc as ss_grpc

log = structlog.get_logger(__name__)

GRPC_ADDR = os.environ.get("ORIGO_STELLARSTATION_MOCK_GRPC_ADDR", "0.0.0.0:50052")
HTTP_PORT = int(os.environ.get("ORIGO_STELLARSTATION_MOCK_HTTP_PORT", "8080"))
TLS_CERT_PATH = os.environ.get("ORIGO_STELLARSTATION_MOCK_TLS_CERT", "/certs/server.crt")
TLS_KEY_PATH = os.environ.get("ORIGO_STELLARSTATION_MOCK_TLS_KEY", "/certs/server.key")

# satellite_id -> Origo Space base URL (e.g. "http://origo-space-sn-001:8080"),
# reachable from *this* container over the shared origo-net Docker network.
# Populated once by the admin API below, at Terrestrial-registration time —
# this process has no other way to know which container a satellite_id relates to.
_registry: dict[str, str] = {}
_http = httpx.AsyncClient(timeout=30.0)


def _now_ts() -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(datetime.now(UTC))
    return ts


# --------------------------------------------------------------------------- gRPC

class StellarStationMockServicer(ss_grpc.StellarStationServiceServicer):
    # ---- booking/discovery: unimplemented, see module docstring --------------
    async def ListUpcomingAvailablePasses(self, request, context):
        return ss.ListUpcomingAvailablePassesResponse()

    async def ListPlans(self, request, context):
        return ss.ListPlansResponse()

    async def ReservePass(self, request, context):
        await context.abort(grpc.StatusCode.UNIMPLEMENTED, "booking isn't part of this demo's runtime path")

    async def CancelPlan(self, request, context):
        return ss.CancelPlanResponse()

    async def AddTle(self, request, context):
        return ss.AddTleResponse()

    async def GetTle(self, request, context):
        await context.abort(grpc.StatusCode.NOT_FOUND, "no TLE registered")

    async def SetTleSource(self, request, context):
        return ss.SetTleSourceResponse()

    async def SetPlanMetadata(self, request, context):
        return ss.SetPlanMetadataResponse()

    # ---- the one RPC this demo actually exercises -----------------------------
    async def OpenSatelliteStream(self, request_iterator, context):
        """Reads exclusively from `request_iterator` (never `context.read()`) — an
        earlier version mixed the two, which is the most likely cause of a real,
        observed bug: the stream sat completely silent for minutes after opening
        (no telemetry sent, no error) until gRPC's own ping-flood protection killed
        the idle connection. That "died from an unrelated symptom, not the real
        cause" shape is exactly what a framework-level read-path deadlock looks
        like — grpc.aio's stream-stream handlers are built around consuming
        `request_iterator` directly; a parallel `context.read()` on the same
        stream very likely contended with it. `context.write()` for outgoing
        messages is unaffected and unchanged — only the read side moved.

        Still not independently verified end to end beyond the one real run that
        surfaced the original bug — same caution as before, verify this
        specifically before trusting anything built on top of it.
        """
        try:
            setup = await request_iterator.__anext__()
        except StopAsyncIteration:  # client disconnected before the setup message arrived
            return

        satellite_id = setup.satellite_id
        space_url = _registry.get(satellite_id)
        if space_url is None:
            await context.abort(
                grpc.StatusCode.NOT_FOUND, f"no Origo Space registered for satellite_id={satellite_id!r}",
            )
            return

        stream_id = setup.stream_id or f"stream-{uuid.uuid4().hex[:12]}"
        enable_flow_control = setup.enable_flow_control
        plan_id = setup.plan_id
        ground_station_id = setup.ground_station_id

        log.info("mock.stream_opened", satellite_id=satellite_id, stream_id=stream_id, space_url=space_url)

        async def send_telemetry(data: bytes) -> None:
            ack_id = f"ack-{uuid.uuid4().hex[:12]}"
            telemetry = ss.Telemetry(
                framing=ss.Framing.BITSTREAM, data=data,
                time_first_byte_received=_now_ts(), time_last_byte_received=_now_ts(),
            )
            await context.write(ss.SatelliteStreamResponse(
                stream_id=stream_id,
                receive_telemetry_response=ss.ReceiveTelemetryResponse(
                    telemetry=[telemetry], plan_id=plan_id, satellite_id=satellite_id,
                    ground_station_id=ground_station_id,
                    message_ack_id=ack_id if enable_flow_control else "",
                ),
            ))

        async def relay_downlink() -> None:
            """One-shot: this mock represents "the satellite is reachable right
            now," not a continuous telemetry feed — matching exactly what a
            KEY_EXCHANGE or DATA_DELIVERY step actually needs from frames(). Same
            stage-drain-or-trigger heuristic origo_info_adapter.dockerlink.adapter
            used, now living behind the real proto instead of a custom REST shape —
            see that module's own docstring for the documented limitation this
            heuristic carries (can't run a fresh key exchange during a pass where
            data happens to be staged)."""
            try:
                status_resp = await _http.get(f"{space_url}/downlink/data/status")
                status_resp.raise_for_status()
                chunks_queued = status_resp.json().get("chunks_queued", 0)
            except httpx.HTTPError as exc:
                log.warning("mock.status_check_failed", error=str(exc))
                chunks_queued = 0

            if chunks_queued > 0:
                while True:
                    try:
                        resp = await _http.post(f"{space_url}/downlink/data")
                    except httpx.HTTPError as exc:
                        log.warning("mock.data_frame_failed", error=str(exc))
                        return
                    if resp.status_code == 404:
                        return
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPError as exc:
                        log.warning("mock.data_frame_failed", error=str(exc))
                        return
                    await send_telemetry(bytes.fromhex(resp.json()["ciphertext_hex"]))
                return

            try:
                resp = await _http.post(f"{space_url}/downlink/trigger")
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("mock.downlink_failed", error=str(exc))
                return
            await send_telemetry(bytes.fromhex(resp.json()["envelope_hex"]))

        async def relay_uplink_loop() -> None:
            """Runs until the client cancels the call (PassExecutor's `async with
            ... as link:` block exiting) — this is what keeps the RPC handler alive
            for the stream's whole lifetime, not relay_downlink() (which finishes
            after its one telemetry push)."""
            async for request in request_iterator:
                if request.WhichOneof("Request") == "send_satellite_commands_request":
                    commands = list(request.send_satellite_commands_request.command)
                    if commands:
                        try:
                            resp = await _http.post(
                                f"{space_url}/uplink", json={"envelope_hex": commands[0].hex()},
                            )
                            resp.raise_for_status()
                        except httpx.HTTPError as exc:
                            log.warning("mock.uplink_failed", error=str(exc))
                            # No command_sent event -> the client's send_commands()
                            # future never resolves and times out — a real failure
                            # signal reaching PassExecutor, not a silent drop.
                            continue
                    await context.write(ss.SatelliteStreamResponse(
                        stream_id=stream_id,
                        stream_event=ss.StreamEvent(
                            request_id=request.request_id, timestamp=_now_ts(),
                            command_sent=ss.StreamEvent.CommandSentFromGroundStation(),
                        ),
                    ))
                # telemetry_received_ack / ground_station_configuration_request:
                # no-op — nothing here maintains a real retransmission buffer or
                # radio state to update.

        downlink_task = asyncio.ensure_future(relay_downlink())
        uplink_task = asyncio.ensure_future(relay_uplink_loop())
        try:
            await asyncio.wait([downlink_task, uplink_task], return_when=asyncio.ALL_COMPLETED)
        finally:
            downlink_task.cancel()
            uplink_task.cancel()
            log.info("mock.stream_closed", satellite_id=satellite_id, stream_id=stream_id)


# --------------------------------------------------------------------------- HTTP admin/relay

app = FastAPI(title="Origo StellarStation mock — admin/relay")


class RegisterSatellite(BaseModel):
    space_url: str


class RelayPeerKey(BaseModel):
    public_key_hex: str


def _require(satellite_id: str) -> str:
    space_url = _registry.get(satellite_id)
    if space_url is None:
        raise HTTPException(404, f"no Origo Space registered for satellite_id={satellite_id!r}")
    return space_url


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/admin/satellites/{satellite_id}")
async def register_satellite(satellite_id: str, body: RegisterSatellite) -> dict[str, str]:
    _registry[satellite_id] = body.space_url.rstrip("/")
    return {"status": "ok"}


@app.delete("/admin/satellites/{satellite_id}")
async def unregister_satellite(satellite_id: str) -> dict[str, str]:
    _registry.pop(satellite_id, None)
    return {"status": "ok"}


@app.get("/admin/satellites/{satellite_id}/health")
async def relay_health(satellite_id: str) -> dict[str, object]:
    """origo-edge's DeviceProvisioner calls this instead of hitting Origo Space's
    own published port directly — the mock is now the only thing that ever talks to
    Origo Space, operationally or during provisioning."""
    resp = await _http.get(f"{_require(satellite_id)}/health")
    resp.raise_for_status()
    return resp.json()


@app.get("/admin/satellites/{satellite_id}/identity")
async def relay_identity(satellite_id: str) -> dict[str, str]:
    resp = await _http.get(f"{_require(satellite_id)}/identity")
    resp.raise_for_status()
    return resp.json()


@app.post("/admin/satellites/{satellite_id}/peer")
async def relay_peer(satellite_id: str, body: RelayPeerKey) -> dict[str, str]:
    resp = await _http.post(f"{_require(satellite_id)}/peer", json={"public_key_hex": body.public_key_hex})
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------------------------------- entrypoint

async def _serve_grpc() -> None:
    server = grpc.aio.server()
    ss_grpc.add_StellarStationServiceServicer_to_server(StellarStationMockServicer(), server)
    creds = grpc.ssl_server_credentials([(Path(TLS_KEY_PATH).read_bytes(), Path(TLS_CERT_PATH).read_bytes())])
    server.add_secure_port(GRPC_ADDR, creds)
    await server.start()
    log.info("mock.grpc_serving", addr=GRPC_ADDR)
    await server.wait_for_termination()


async def _serve_http() -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=HTTP_PORT, log_level="warning")
    await uvicorn.Server(config).serve()


async def serve() -> None:
    await asyncio.gather(_serve_grpc(), _serve_http())


if __name__ == "__main__":
    asyncio.run(serve())