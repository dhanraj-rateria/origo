"""Provider-neutral ground-network domain types.

Frozen by design: these cross a boundary, and an adapter caller mutating a returned
window is a bug that is very hard to trace back.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import NewType, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProviderId = NewType("ProviderId", str)
ContactId = NewType("ContactId", str)          # provider's durable plan identifier
SatelliteRef = NewType("SatelliteRef", str)    # provider's satellite identifier
StationRef = NewType("StationRef", str)        # provider's ground-station identifier
ChannelSetRef = NewType("ChannelSetRef", str)

STELLARSTATION = ProviderId("STELLARSTATION")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ContactPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Band(StrEnum):
    """Origo's own band taxonomy. Providers describe channel sets by frequency, not by
    a band label, so this is derived in mapping, not read from the wire."""

    UHF = "UHF"
    S_BAND = "S_BAND"
    X_BAND = "X_BAND"
    KA_BAND = "KA_BAND"
    UNKNOWN = "UNKNOWN"


class ContactStatus(StrEnum):
    RESERVED = "RESERVED"
    EXECUTING = "EXECUTING"
    PROCESSING = "PROCESSING"      # provider post-processing after LOS
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_terminal(self) -> bool:
        return self in {
            ContactStatus.SUCCEEDED,
            ContactStatus.FAILED,
            ContactStatus.CANCELED,
        }


class FrameEncoding(StrEnum):
    BITSTREAM = "BITSTREAM"
    AX25 = "AX25"
    IQ = "IQ"
    IMAGE_PNG = "IMAGE_PNG"
    IMAGE_JPEG = "IMAGE_JPEG"
    FREE_TEXT_UTF8 = "FREE_TEXT_UTF8"
    WATERFALL = "WATERFALL"
    UNKNOWN = "UNKNOWN"


class GeoPoint(_Frozen):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class StationInfo(_Frozen):
    station_ref: StationRef
    location: GeoPoint | None = None
    country_code: str | None = None
    organization_name: str | None = None


class ChannelSetInfo(_Frozen):
    channel_set_ref: ChannelSetRef
    name: str | None = None
    uplink_center_frequency_hz: int | None = None
    downlink_center_frequency_hz: int | None = None
    band: Band = Band.UNKNOWN


class ContactOption(_Frozen):
    """One bookable configuration on a ContactWindow.

    `reservation_token` is an ephemeral, single-use bearer credential. It MUST NOT be
    persisted, logged, or returned over Origo's own API — see ARCHITECTURE §0.2. It is
    excluded from repr and from model_dump() by default for exactly that reason.
    """

    channel_set: ChannelSetInfo
    unit_price: float | None = None
    reservation_token: str = Field(repr=False, exclude=True)

    def __str__(self) -> str:
        return f"ContactOption({self.channel_set.channel_set_ref}, {self.channel_set.band})"


class ContactWindow(_Frozen):
    """A predicted, not-yet-booked contact opportunity. Provider `Pass`."""

    provider: ProviderId
    satellite_ref: SatelliteRef
    station: StationInfo
    aos: datetime
    los: datetime
    max_elevation_deg: float
    max_elevation_at: datetime | None = None
    options: tuple[ContactOption, ...] = ()

    @property
    def duration(self) -> timedelta:
        return self.los - self.aos

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.aos.tzinfo is None or self.los.tzinfo is None:
            raise ValueError("aos/los must be timezone-aware")
        if self.los <= self.aos:
            raise ValueError(f"los ({self.los}) must be after aos ({self.aos})")
        return self

    def option_for_band(self, band: Band) -> ContactOption | None:
        return next((o for o in self.options if o.channel_set.band is band), None)

    def cheapest_option(self) -> ContactOption | None:
        priced = [o for o in self.options if o.unit_price is not None]
        return min(priced, key=lambda o: o.unit_price or 0.0) if priced else None


class Contact(_Frozen):
    """A booked contact. Provider `Plan`. `contact_id` is durable — persist this."""

    provider: ProviderId
    contact_id: ContactId
    satellite_ref: SatelliteRef
    station: StationInfo
    status: ContactStatus
    aos: datetime
    los: datetime
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    max_elevation_deg: float | None = None
    max_elevation_at: datetime | None = None
    channel_set: ChannelSetInfo | None = None
    priority: ContactPriority = ContactPriority.MEDIUM
    unit_price: float | None = None
    telemetry_artifacts: tuple[TelemetryArtifact, ...] = ()


class TelemetryArtifact(_Frozen):
    """Post-pass bulk telemetry made available by the provider at a URL."""

    url: str
    data_type: str      # RAW | DEMODULATED | DECODED


class DownlinkFrame(_Frozen):
    """Bytes off the satellite. For a KEY_EXCHANGE job this carries the signed `ek`
    (design §5.2 step 4). The adapter does not parse or interpret `data` — framing above
    the byte level is the HSM's and the Edge Agent's business, not the transport's."""

    encoding: FrameEncoding
    data: bytes = Field(repr=False)
    downlink_frequency_hz: int | None = None
    first_byte_at: datetime | None = None
    last_byte_at: datetime | None = None
    frame_header: bytes | None = Field(default=None, repr=False)


class TleSet(_Frozen):
    line1: str = Field(min_length=69, max_length=69)
    line2: str = Field(min_length=69, max_length=69)

    @model_validator(mode="after")
    def _check_lines(self) -> Self:
        if not self.line1.startswith("1 "):
            raise ValueError("TLE line1 must begin with '1 '")
        if not self.line2.startswith("2 "):
            raise ValueError("TLE line2 must begin with '2 '")
        return self


class CommandAck(_Frozen):
    """Provider confirmation that an uplink burst left the ground station."""

    request_id: str
    sent_at: datetime | None = None