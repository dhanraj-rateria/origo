"""OpenSatelliteStream wrapper: the live byte pipe during a contact."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from types import TracebackType

import grpc
import structlog

from .._grpc_errors import translate
from ..clock import utcnow
from ..errors import StreamClosed
from ..models import ChannelSetRef, CommandAck, ContactId, DownlinkFrame, SatelliteRef
from . import mapping as m
from .._proto.stellarstation.api.v1 import stellarstation_pb2 as ss
from .._proto.stellarstation.api.v1 import stellarstation_pb2_grpc as ss_grpc
from .config import StellarStationSettings

log = structlog.get_logger(__name__)

_SENTINEL = object()


class StellarStationLink:
    """One bidirectional satellite stream.

    Contract notes that are easy to get wrong and expensive to discover at AOS:

    * `satellite_id` must be set on **every** request message, not just the first.
    * `enable_events` / `enable_flow_control` are honoured only on the setup message.
    * With flow control on, each ReceiveTelemetryResponse must be acked by
      `message_ack_id`. Unacked messages stall the stream. We ack automatically inside
      `frames()` so a caller cannot forget.
    * Resuming needs both `stream_id` and `resume_stream_message_ack_id`; the server
      rewinds to the message *after* that ack id.
    """

    def __init__(
        self,
        *,
        stub: ss_grpc.StellarStationServiceStub,
        settings: StellarStationSettings,
        satellite_ref: SatelliteRef,
        contact_id: ContactId | None = None,
        station_ref: str | None = None,
        resume_stream_id: str | None = None,
        resume_after_ack_id: str | None = None,
    ) -> None:
        self._stub = stub
        self._settings = settings
        self._satellite_ref = satellite_ref
        self._contact_id = contact_id
        self._station_ref = station_ref
        self._stream_id: str | None = resume_stream_id
        self._last_ack_id: str | None = resume_after_ack_id

        self._outbound: asyncio.Queue[object] = asyncio.Queue()
        self._call: grpc.aio.StreamStreamCall | None = None
        self._acks: dict[str, asyncio.Future[CommandAck]] = {}
        self._closed = False

    # ---------------------------------------------------------------- properties

    @property
    def stream_id(self) -> str | None:
        return self._stream_id

    @property
    def last_ack_id(self) -> str | None:
        return self._last_ack_id

    # ---------------------------------------------------------------- lifecycle

    async def __aenter__(self) -> StellarStationLink:
        self._call = self._stub.OpenSatelliteStream(self._requests())
        await self._outbound.put(self._setup_request())
        log.info(
            "link.opened",
            satellite_ref=self._satellite_ref,
            contact_id=self._contact_id,
            resuming=self._stream_id is not None,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._outbound.put(_SENTINEL)
        if self._call is not None:
            self._call.cancel()
        for fut in self._acks.values():
            if not fut.done():
                fut.set_exception(StreamClosed("link closed before command ack"))
        self._acks.clear()
        log.info(
            "link.closed",
            satellite_ref=self._satellite_ref,
            stream_id=self._stream_id,
            last_ack_id=self._last_ack_id,
        )

    # ---------------------------------------------------------------- requests

    def _setup_request(self) -> ss.SatelliteStreamRequest:
        req = ss.SatelliteStreamRequest(
            satellite_id=self._satellite_ref,
            enable_events=self._settings.enable_stream_events,
            enable_flow_control=self._settings.enable_flow_control,
        )
        if self._contact_id:
            req.plan_id = self._contact_id
        if self._station_ref:
            req.ground_station_id = self._station_ref
        if self._stream_id:
            req.stream_id = self._stream_id
        if self._last_ack_id:
            req.resume_stream_message_ack_id = self._last_ack_id
        return req

    async def _requests(self) -> AsyncIterator[ss.SatelliteStreamRequest]:
        while True:
            item = await self._outbound.get()
            if item is _SENTINEL:
                return
            yield item  # type: ignore[misc]

    # ---------------------------------------------------------------- downlink

    async def frames(self) -> AsyncIterator[DownlinkFrame]:
        """Yield downlink frames until LOS or close, acking as we go.

        Per design §5.2 step 4 this is where the signed `ek` arrives. We hand up raw
        bytes: reassembly and signature verification belong to the Edge Agent and the
        Ground HSM (§3.3.1, §3.4), never to the transport.
        """
        if self._call is None:
            raise StreamClosed("frames() before __aenter__")

        try:
            async for response in self._call:
                if response.stream_id and response.stream_id != self._stream_id:
                    self._stream_id = response.stream_id

                kind = response.WhichOneof("Response")
                if kind == "receive_telemetry_response":
                    tlm = response.receive_telemetry_response
                    for pb in tlm.telemetry:
                        yield m.to_frame(pb)
                    if tlm.message_ack_id:
                        await self._ack(tlm.message_ack_id)
                elif kind == "stream_event":
                    self._handle_event(response.stream_event)
        except grpc.aio.AioRpcError as exc:
            recoverable = exc.code() in {
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
                grpc.StatusCode.INTERNAL,
            }
            raise StreamClosed(
                f"satellite stream ended: {exc.details() or exc.code().name}",
                recoverable=recoverable and self._last_ack_id is not None,
                provider="STELLARSTATION",
                cause=exc,
            ) from exc

    async def _ack(self, message_ack_id: str) -> None:
        if not self._settings.enable_flow_control:
            return
        self._last_ack_id = message_ack_id
        await self._outbound.put(
            ss.SatelliteStreamRequest(
                satellite_id=self._satellite_ref,
                telemetry_received_ack=ss.ReceiveTelemetryAck(
                    message_ack_id=message_ack_id,
                    received_timestamp=m.from_dt(utcnow()),
                ),
            )
        )

    def _handle_event(self, event: ss.StreamEvent) -> None:
        kind = event.WhichOneof("Event")
        if kind == "command_sent":
            fut = self._acks.pop(event.request_id, None)
            if fut is not None and not fut.done():
                fut.set_result(
                    CommandAck(
                        request_id=event.request_id, sent_at=m.to_dt(event.timestamp)
                    )
                )
        elif kind == "plan_monitoring_event":
            # Station config / state / lifecycle. Surface as telemetry rather than
            # acting on it here — the link is transport, not a decision-maker.
            log.debug(
                "link.monitoring_event",
                contact_id=event.plan_monitoring_event.plan_id,
                info=event.plan_monitoring_event.WhichOneof("Info"),
            )

    # ---------------------------------------------------------------- uplink

    async def send_commands(
        self,
        commands: Sequence[bytes],
        *,
        channel_set_ref: ChannelSetRef,
        request_id: str | None = None,
        timeout_sec: float = 30.0,
    ) -> CommandAck:
        """Uplink a burst and wait for the station's confirmation.

        Per §5.2 step 6 this carries the signed `ct`. Awaiting the ack is what lets the
        Pass Executor mark the step failed and move on within the window, rather than
        assuming success and discovering it after LOS.
        """
        if self._call is None:
            raise StreamClosed("send_commands() before __aenter__")
        if not commands:
            raise ValueError("send_commands() called with no commands")

        rid = request_id or f"origo-{uuid.uuid4()}"
        fut: asyncio.Future[CommandAck] = asyncio.get_running_loop().create_future()
        self._acks[rid] = fut

        await self._outbound.put(
            ss.SatelliteStreamRequest(
                satellite_id=self._satellite_ref,
                request_id=rid,
                send_satellite_commands_request=ss.SendSatelliteCommandsRequest(
                    command=list(commands), channel_set_id=channel_set_ref
                ),
            )
        )
        log.info(
            "link.commands_queued",
            request_id=rid,
            count=len(commands),
            total_bytes=sum(len(c) for c in commands),   # size, never content
        )

        try:
            return await asyncio.wait_for(fut, timeout=timeout_sec)
        except TimeoutError as exc:
            self._acks.pop(rid, None)
            raise StreamClosed(
                f"no confirmation for command burst {rid} within {timeout_sec}s"
            ) from exc

    async def configure_radio(
        self,
        *,
        downlink_bitrate: float | None = None,
        uplink_bitrate: float | None = None,
        enable_carrier: bool | None = None,
        enable_if_modulation: bool | None = None,
        enable_idle_pattern: bool | None = None,
    ) -> None:
        """Adjust station radio mid-pass. Unset fields are left alone — the proto uses
        wrapper types precisely so 'unset' and 'false' are distinguishable."""
        from google.protobuf import wrappers_pb2 as w

        tx = ss.TransmitterConfigurationRequest()
        if enable_carrier is not None:
            tx.enable_carrier.CopyFrom(w.BoolValue(value=enable_carrier))
        if enable_if_modulation is not None:
            tx.enable_if_modulation.CopyFrom(w.BoolValue(value=enable_if_modulation))
        if enable_idle_pattern is not None:
            tx.enable_idle_pattern.CopyFrom(w.BoolValue(value=enable_idle_pattern))
        if uplink_bitrate is not None:
            tx.bitrate.CopyFrom(w.FloatValue(value=uplink_bitrate))

        rx = ss.ReceiverConfigurationRequest()
        if downlink_bitrate is not None:
            rx.bitrate.CopyFrom(w.FloatValue(value=downlink_bitrate))

        await self._outbound.put(
            ss.SatelliteStreamRequest(
                satellite_id=self._satellite_ref,
                ground_station_configuration_request=ss.GroundStationConfigurationRequest(
                    transmitter_configuration_request=tx,
                    receiver_configuration_request=rx,
                ),
            )
        )