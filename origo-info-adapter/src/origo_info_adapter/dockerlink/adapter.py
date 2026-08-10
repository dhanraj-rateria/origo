"""GroundNetworkAdapter backed by a direct network hop to an Origo Space container.

This is the mocked half of the Docker device loop: real bytes cross a real
container-to-container network link, but there is no S-band physics, no orbit
geometry, and no Infostellar API call anywhere in this file — a "pass" is simply
"call the satellite container's HTTP endpoint right now." Swapping this back out for
the real StellarStationAdapter later touches only build_adapter() in ../__init__.py —
nothing upstream (pass_executor.py, main.py) changes, which is the entire point of
GroundNetworkAdapter being a Protocol.

Scope: only what a KEY_EXCHANGE step actually calls (`open_link`, `frames`,
`send_commands`, plus lifecycle/health). The booking/discovery surface
(`list_contact_windows`, `reserve_contact`, ...) has no meaning for a direct link and
raises NotImplementedError rather than pretending to support a booking model that
doesn't exist here — DATA_DELIVERY and multi-frame downlinks aren't wired through
this adapter either; InMemoryAdapter remains the right fake for exercising those in
tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from types import TracebackType

import httpx
import structlog

from ..errors import AdapterUnavailable
from ..models import (
    ChannelSetRef, CommandAck, Contact, ContactId, ContactPriority, ContactWindow,
    DownlinkFrame, FrameEncoding, ProviderId, SatelliteRef, TleSet,
)

log = structlog.get_logger(__name__)

DOCKER_LINK = ProviderId("DOCKER_LINK")


class DockerLinkAdapter:
    """Satisfies GroundNetworkAdapter structurally. One instance talks to one Origo
    Space device's HTTP sidecar (origo_space.server), reached by Docker container-name
    DNS on the shared device network — see origo-edge's DeviceProvisioner, which sets
    ORIGO_RF_LINK_URL to this value when it provisions a station-agent container."""

    def __init__(self, *, base_url: str, timeout_sec: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sec

    @property
    def provider(self) -> ProviderId:
        return DOCKER_LINK

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def open_link(self, *, satellite_ref: SatelliteRef, **_: object) -> DockerLink:
        return DockerLink(base_url=self._base_url, timeout_sec=self._timeout)

    # --- no booking model for a direct container-to-container link -------------
    async def list_contact_windows(self, *, satellite_ref: SatelliteRef) -> list[ContactWindow]:
        raise NotImplementedError("DockerLinkAdapter has no contact-window model — see module docstring")

    async def reserve_contact(
        self, *, reservation_token: str, priority: ContactPriority = ContactPriority.MEDIUM,
    ) -> Contact:
        raise NotImplementedError("DockerLinkAdapter has no booking model — see module docstring")

    async def cancel_contact(self, *, contact_id: ContactId) -> None:
        raise NotImplementedError("DockerLinkAdapter has no booking model — see module docstring")

    async def list_contacts(
        self, *, satellite_ref: SatelliteRef, aos_after: datetime, aos_before: datetime,
    ) -> list[Contact]:
        return []

    async def get_contact(self, *, satellite_ref: SatelliteRef, contact_id: ContactId) -> Contact | None:
        return None

    async def tag_contact(self, *, contact_id: ContactId, tags: Mapping[str, Sequence[str]]) -> None:
        return None

    async def push_ephemeris(self, *, satellite_ref: SatelliteRef, tle: TleSet) -> None:
        return None

    async def get_ephemeris(self, *, satellite_ref: SatelliteRef) -> TleSet | None:
        return None


class DockerLink:
    """One 'pass' = one HTTP round trip to the Origo Space container, in each
    direction. `frames()` yields at most one frame (the ek envelope) — a real RF pass
    downlinks continuously; this mock represents "the satellite is reachable right
    now," which is all a KEY_EXCHANGE step needs."""

    def __init__(self, *, base_url: str, timeout_sec: float) -> None:
        self._base_url = base_url
        self._timeout = timeout_sec
        self._client: httpx.AsyncClient | None = None
        self._last_ack_id: str | None = None

    @property
    def stream_id(self) -> str | None:
        return None

    @property
    def last_ack_id(self) -> str | None:
        return self._last_ack_id

    async def __aenter__(self) -> DockerLink:
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def frames(self) -> AsyncIterator[DownlinkFrame]:
        assert self._client is not None
        try:
            resp = await self._client.post(f"{self._base_url}/downlink/trigger")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("dockerlink.downlink_failed", error=str(exc))
            return   # no frame yielded -> pass_executor reports "link closed before ek arrived"
        body = resp.json()
        now = datetime.now(UTC)
        self._last_ack_id = "docker-ack-0"
        yield DownlinkFrame(
            encoding=FrameEncoding.BITSTREAM, data=bytes.fromhex(body["envelope_hex"]),
            first_byte_at=now, last_byte_at=now,
        )

    async def send_commands(
        self,
        commands: Sequence[bytes],
        *,
        channel_set_ref: ChannelSetRef,
        request_id: str | None = None,
        timeout_sec: float = 30.0,
    ) -> CommandAck:
        assert self._client is not None
        rid = request_id or "docker-req-0"
        # One burst, one ct envelope — see pass_executor._frame_ct.
        try:
            resp = await self._client.post(
                f"{self._base_url}/uplink", json={"envelope_hex": commands[0].hex()},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterUnavailable(f"uplink to {self._base_url} failed: {exc}", provider=DOCKER_LINK) from exc
        return CommandAck(request_id=rid, sent_at=datetime.now(UTC))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
