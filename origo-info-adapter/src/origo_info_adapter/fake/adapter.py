"""In-memory GroundNetworkAdapter for dev, CI, and demos.

Deliberately implements the *same* awkward semantics as the real provider: single-use
tokens, a pre-AOS cancellation lockout, terminal-status transitions. A fake that is
kinder than production is a fake that hides bugs.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime, timedelta
from types import TracebackType

from ..clock import Clock, SystemClock
from ..errors import (
    ContactAlreadyExecuted, ContactNotCancellable, ContactNotFound,
    ReservationTokenRejected,
)
from ..models import (
    Band, ChannelSetInfo, ChannelSetRef, CommandAck, Contact, ContactId, ContactOption,
    ContactPriority, ContactStatus, ContactWindow, DownlinkFrame, FrameEncoding,
    GeoPoint, ProviderId, SatelliteRef, StationInfo, StationRef, TleSet,
)

FAKE = ProviderId("FAKE")
CANCEL_LOCKOUT = timedelta(minutes=10)

_S_BAND = ChannelSetInfo(
    channel_set_ref=ChannelSetRef("cs-s-band"), name="S-band TT&C",
    uplink_center_frequency_hz=2_050_000_000,
    downlink_center_frequency_hz=2_250_000_000, band=Band.S_BAND,
)
_X_BAND = ChannelSetInfo(
    channel_set_ref=ChannelSetRef("cs-x-band"), name="X-band payload",
    downlink_center_frequency_hz=8_200_000_000, band=Band.X_BAND,
)
_STATIONS = (
    StationInfo(station_ref=StationRef("gs-awarua"),
                location=GeoPoint(lat=-46.53, lon=168.38), country_code="NZ",
                organization_name="Fake Network"),
    StationInfo(station_ref=StationRef("gs-svalbard"),
                location=GeoPoint(lat=78.23, lon=15.41), country_code="NO",
                organization_name="Fake Network"),
)


class InMemoryAdapter:
    """Satisfies GroundNetworkAdapter structurally — no inheritance needed."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        window_count: int = 6,
        downlink_script: Sequence[bytes] = (),
    ) -> None:
        self._clock = clock or SystemClock()
        self._window_count = window_count
        self._downlink_script = list(downlink_script)
        self._tokens: dict[str, tuple[SatelliteRef, ContactWindow, ContactOption]] = {}
        self._contacts: dict[ContactId, Contact] = {}
        self._tags: dict[ContactId, dict[str, list[str]]] = {}
        self._tles: dict[SatelliteRef, TleSet] = {}
        self.uplinked: list[tuple[str, list[bytes]]] = []   # test assertions

    @property
    def provider(self) -> ProviderId:
        return FAKE

    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def health(self) -> bool:
        return True

    async def list_contact_windows(
        self, *, satellite_ref: SatelliteRef
    ) -> list[ContactWindow]:
        now = self._clock.now()
        windows: list[ContactWindow] = []
        for i in range(self._window_count):
            aos = now + timedelta(minutes=45 * (i + 1))
            station = _STATIONS[i % len(_STATIONS)]
            options: list[ContactOption] = []
            for cs, price in ((_S_BAND, 12.5), (_X_BAND, 48.0)):
                token = f"fake-token-{uuid.uuid4()}"
                options.append(
                    ContactOption(channel_set=cs, unit_price=price, reservation_token=token)
                )
            window = ContactWindow(
                provider=FAKE, satellite_ref=satellite_ref, station=station,
                aos=aos, los=aos + timedelta(minutes=8, seconds=30),
                max_elevation_deg=25.0 + (i * 11) % 60,
                max_elevation_at=aos + timedelta(minutes=4),
                options=tuple(options),
            )
            for opt in options:
                self._tokens[opt.reservation_token] = (satellite_ref, window, opt)
            windows.append(window)
        return windows

    async def reserve_contact(
        self, *, reservation_token: str,
        priority: ContactPriority = ContactPriority.MEDIUM,
    ) -> Contact:
        entry = self._tokens.pop(reservation_token, None)   # pop == single use
        if entry is None:
            raise ReservationTokenRejected(
                "unknown or already-consumed reservation token", provider=self.provider
            )
        satellite_ref, window, option = entry
        contact = Contact(
            provider=FAKE, contact_id=ContactId(f"fake-plan-{uuid.uuid4().hex[:12]}"),
            satellite_ref=satellite_ref, station=window.station,
            status=ContactStatus.RESERVED, aos=window.aos, los=window.los,
            scheduled_start=window.aos - timedelta(minutes=2),
            scheduled_end=window.los + timedelta(minutes=2),
            max_elevation_deg=window.max_elevation_deg,
            max_elevation_at=window.max_elevation_at,
            channel_set=option.channel_set, priority=priority,
            unit_price=option.unit_price,
        )
        self._contacts[contact.contact_id] = contact
        return contact

    async def cancel_contact(self, *, contact_id: ContactId) -> None:
        contact = self._contacts.get(contact_id)
        if contact is None:
            raise ContactNotFound(f"no contact {contact_id}", provider=self.provider)
        if contact.status is ContactStatus.CANCELED:
            raise ContactNotCancellable("already cancelled", provider=self.provider)
        if contact.status is not ContactStatus.RESERVED:
            raise ContactAlreadyExecuted(
                f"contact is {contact.status}", provider=self.provider
            )
        if contact.aos - self._clock.now() < CANCEL_LOCKOUT:
            raise ContactNotCancellable(
                "inside the 10-minute pre-AOS lockout", provider=self.provider
            )
        self._contacts[contact_id] = contact.model_copy(
            update={"status": ContactStatus.CANCELED}
        )

    async def list_contacts(
        self, *, satellite_ref: SatelliteRef,
        aos_after: datetime, aos_before: datetime,
    ) -> list[Contact]:
        return sorted(
            (
                c for c in self._contacts.values()
                if c.satellite_ref == satellite_ref and aos_after <= c.aos < aos_before
            ),
            key=lambda c: c.aos,
        )

    async def get_contact(
        self, *, satellite_ref: SatelliteRef, contact_id: ContactId
    ) -> Contact | None:
        contact = self._contacts.get(contact_id)
        return contact if contact and contact.satellite_ref == satellite_ref else None

    async def tag_contact(
        self, *, contact_id: ContactId, tags: Mapping[str, Sequence[str]]
    ) -> None:
        if contact_id not in self._contacts:
            raise ContactNotFound(f"no contact {contact_id}", provider=self.provider)
        self._tags.setdefault(contact_id, {}).update({k: list(v) for k, v in tags.items()})

    async def push_ephemeris(self, *, satellite_ref: SatelliteRef, tle: TleSet) -> None:
        self._tles[satellite_ref] = tle

    async def get_ephemeris(self, *, satellite_ref: SatelliteRef) -> TleSet | None:
        return self._tles.get(satellite_ref)

    def open_link(self, *, satellite_ref: SatelliteRef, **_: object) -> InMemoryLink:
        return InMemoryLink(self, satellite_ref)

    # test helpers
    def force_status(self, contact_id: ContactId, status: ContactStatus) -> None:
        self._contacts[contact_id] = self._contacts[contact_id].model_copy(
            update={"status": status}
        )

    def tags_for(self, contact_id: ContactId) -> dict[str, list[str]]:
        return dict(self._tags.get(contact_id, {}))


class InMemoryLink:
    def __init__(self, parent: InMemoryAdapter, satellite_ref: SatelliteRef) -> None:
        self._parent = parent
        self._satellite_ref = satellite_ref
        self._stream_id = f"fake-stream-{uuid.uuid4().hex[:8]}"
        self._last_ack_id: str | None = None

    @property
    def stream_id(self) -> str | None:
        return self._stream_id

    @property
    def last_ack_id(self) -> str | None:
        return self._last_ack_id

    async def __aenter__(self) -> InMemoryLink:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None,
        exc: BaseException | None, tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def frames(self) -> AsyncIterator[DownlinkFrame]:
        now = self._parent._clock.now()
        for i, payload in enumerate(self._parent._downlink_script):
            self._last_ack_id = f"fake-ack-{i}"
            yield DownlinkFrame(
                encoding=FrameEncoding.BITSTREAM, data=payload,
                downlink_frequency_hz=2_250_000_000,
                first_byte_at=now, last_byte_at=now,
            )

    async def send_commands(
        self, commands: Sequence[bytes], *,
        channel_set_ref: ChannelSetRef, request_id: str | None = None,
        timeout_sec: float = 30.0,
    ) -> CommandAck:
        rid = request_id or f"fake-req-{uuid.uuid4().hex[:8]}"
        self._parent.uplinked.append((rid, list(commands)))
        return CommandAck(request_id=rid, sent_at=self._parent._clock.now())

    async def close(self) -> None: ...