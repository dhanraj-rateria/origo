"""Pure protobuf <-> domain translation. No I/O, no state, no logging."""

from __future__ import annotations

from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp

from ..models import (
    Band, ChannelSetInfo, ChannelSetRef, Contact, ContactId, ContactOption,
    ContactPriority, ContactStatus, ContactWindow, DownlinkFrame, FrameEncoding,
    GeoPoint, STELLARSTATION, SatelliteRef, StationInfo, StationRef,
    TelemetryArtifact, TleSet,
)
from .._proto.stellarstation.api.v1 import stellarstation_pb2 as ss
from .._proto.stellarstation.api.v1 import transport_pb2 as tp
from .._proto.stellarstation.api.v1.orbit import orbit_pb2 as orbit

# ---------------------------------------------------------------- timestamps

def to_dt(ts: Timestamp) -> datetime | None:
    """Proto Timestamp -> aware UTC datetime. Unset (epoch 0) maps to None.

    proto3 has no null, so an unset Timestamp is indistinguishable from 1970-01-01.
    Every consumer wants None there, and forgetting this is how a pass ends up
    scheduled for the Nixon administration.
    """
    if ts is None or (ts.seconds == 0 and ts.nanos == 0):
        return None
    return datetime.fromtimestamp(ts.seconds + ts.nanos / 1e9, tz=UTC)


def to_dt_required(ts: Timestamp, field: str) -> datetime:
    value = to_dt(ts)
    if value is None:
        raise ValueError(f"required timestamp '{field}' was unset")
    return value


def from_dt(dt: datetime) -> Timestamp:
    if dt.tzinfo is None:
        raise ValueError("refusing to serialise a naive datetime")
    ts = Timestamp()
    ts.FromDatetime(dt.astimezone(UTC))
    return ts


# ---------------------------------------------------------------- enums

_STATUS: dict[int, ContactStatus] = {
    ss.Plan.Status.RESERVED: ContactStatus.RESERVED,
    ss.Plan.Status.EXECUTING: ContactStatus.EXECUTING,
    ss.Plan.Status.SUCCEEDED: ContactStatus.SUCCEEDED,
    ss.Plan.Status.FAILED: ContactStatus.FAILED,
    ss.Plan.Status.CANCELED: ContactStatus.CANCELED,
    ss.Plan.Status.PROCESSING: ContactStatus.PROCESSING,
}

_PRIORITY_TO_PB: dict[ContactPriority, int] = {
    ContactPriority.LOW: ss.Priority.LOW,
    ContactPriority.MEDIUM: ss.Priority.MEDIUM,
    ContactPriority.HIGH: ss.Priority.HIGH,
}
_PRIORITY_FROM_PB = {v: k for k, v in _PRIORITY_TO_PB.items()}

_FRAMING: dict[int, FrameEncoding] = {
    tp.Framing.BITSTREAM: FrameEncoding.BITSTREAM,
    tp.Framing.AX25: FrameEncoding.AX25,
    tp.Framing.IQ: FrameEncoding.IQ,
    tp.Framing.IMAGE_PNG: FrameEncoding.IMAGE_PNG,
    tp.Framing.IMAGE_JPEG: FrameEncoding.IMAGE_JPEG,
    tp.Framing.FREE_TEXT_UTF8: FrameEncoding.FREE_TEXT_UTF8,
    tp.Framing.WATERFALL: FrameEncoding.WATERFALL,
}
_FRAMING_TO_PB = {v: k for k, v in _FRAMING.items()}

_ARTIFACT_TYPE: dict[int, str] = {
    ss.TelemetryMetadata.DataType.RAW: "RAW",
    ss.TelemetryMetadata.DataType.DEMODULATED: "DEMODULATED",
    ss.TelemetryMetadata.DataType.DECODED: "DECODED",
}


def to_status(v: int) -> ContactStatus:
    return _STATUS.get(v, ContactStatus.UNKNOWN)


def to_priority(v: int) -> ContactPriority:
    return _PRIORITY_FROM_PB.get(v, ContactPriority.MEDIUM)


def from_priority(p: ContactPriority) -> int:
    return _PRIORITY_TO_PB[p]


def to_encoding(v: int) -> FrameEncoding:
    return _FRAMING.get(v, FrameEncoding.UNKNOWN)


def from_encoding(e: FrameEncoding) -> int:
    if e is FrameEncoding.UNKNOWN:
        raise ValueError("cannot serialise FrameEncoding.UNKNOWN")
    return _FRAMING_TO_PB[e]


# ---------------------------------------------------------------- band derivation

# Inclusive-lower, exclusive-upper Hz bounds, IEEE letter bands.
_BANDS: tuple[tuple[int, int, Band], ...] = (
    (300_000_000, 1_000_000_000, Band.UHF),
    (2_000_000_000, 4_000_000_000, Band.S_BAND),
    (8_000_000_000, 12_000_000_000, Band.X_BAND),
    (26_500_000_000, 40_000_000_000, Band.KA_BAND),
)


def band_for_frequency(hz: int | None) -> Band:
    if not hz:
        return Band.UNKNOWN
    return next((b for lo, hi, b in _BANDS if lo <= hz < hi), Band.UNKNOWN)


# ---------------------------------------------------------------- structures

def to_channel_set(pb: ss.ChannelSet) -> ChannelSetInfo:
    """Downlink frequency decides the band: the downlink is what the payload uses and
    what a data-delivery job is scheduled against."""
    up = _center_hz(pb.uplink) if pb.HasField("uplink") else None
    down = _center_hz(pb.downlink) if pb.HasField("downlink") else None
    return ChannelSetInfo(
        channel_set_ref=ChannelSetRef(pb.id),
        name=pb.name or None,
        uplink_center_frequency_hz=up,
        downlink_center_frequency_hz=down,
        band=band_for_frequency(down or up),
    )


def _center_hz(cfg: object) -> int | None:
    """Read a centre frequency out of radio.RadioDeviceConfiguration defensively.

    Radio config is the part of the provider schema most likely to change, and it is
    not worth an exception in the scheduler if a field is renamed — band is advisory,
    channel_set_ref is authoritative.
    """
    for attr in ("center_frequency_hz", "centre_frequency_hz", "frequency_hz"):
        value = getattr(cfg, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    return None


def to_station_from_pass(pb: ss.Pass) -> StationInfo:
    return StationInfo(
        station_ref=StationRef(pb.ground_station_id),
        location=_point(pb.ground_station_latitude, pb.ground_station_longitude),
        country_code=pb.ground_station_country_code or None,
        organization_name=pb.ground_station_organization_name or None,
    )


def to_station_from_plan(pb: ss.Plan) -> StationInfo:
    return StationInfo(
        station_ref=StationRef(pb.ground_station_id),
        location=_point(pb.ground_station_latitude, pb.ground_station_longitude),
        country_code=pb.ground_station_country_code or None,
        organization_name=pb.ground_station_organization_name or None,
    )


def _point(lat: float, lon: float) -> GeoPoint | None:
    # (0, 0) is Null Island, not a ground station.
    if lat == 0.0 and lon == 0.0:
        return None
    return GeoPoint(lat=lat, lon=lon)


def to_contact_window(pb: ss.Pass, *, satellite_ref: SatelliteRef) -> ContactWindow:
    """`Pass` carries no satellite_id — it was implied by the request. Thread it in."""
    return ContactWindow(
        provider=STELLARSTATION,
        satellite_ref=satellite_ref,
        station=to_station_from_pass(pb),
        aos=to_dt_required(pb.aos_time, "aos_time"),
        los=to_dt_required(pb.los_time, "los_time"),
        max_elevation_deg=pb.max_elevation_degrees,
        max_elevation_at=to_dt(pb.max_elevation_time),
        options=tuple(
            ContactOption(
                channel_set=to_channel_set(t.channel_set),
                unit_price=t.unit_price or None,
                reservation_token=t.reservation_token,
            )
            for t in pb.channel_set_token
        ),
    )


def to_contact(pb: ss.Plan) -> Contact:
    return Contact(
        provider=STELLARSTATION,
        contact_id=ContactId(pb.id),
        satellite_ref=SatelliteRef(pb.satellite_id),
        station=to_station_from_plan(pb),
        status=to_status(pb.status),
        aos=to_dt_required(pb.aos_time, "aos_time"),
        los=to_dt_required(pb.los_time, "los_time"),
        # start/end_time are the *billed* window, wider than AOS/LOS (setup + teardown).
        # Bill against these; schedule jobs against AOS/LOS.
        scheduled_start=to_dt(pb.start_time),
        scheduled_end=to_dt(pb.end_time),
        max_elevation_deg=pb.max_elevation_degrees or None,
        max_elevation_at=to_dt(pb.max_elevation_time),
        channel_set=to_channel_set(pb.channel_set) if pb.HasField("channel_set") else None,
        priority=to_priority(pb.priority),
        unit_price=pb.unit_price or None,
        telemetry_artifacts=tuple(
            TelemetryArtifact(
                url=m.url, data_type=_ARTIFACT_TYPE.get(m.data_type, "RAW")
            )
            for m in pb.telemetry_metadata
        ),
    )


def to_frame(pb: tp.Telemetry) -> DownlinkFrame:
    return DownlinkFrame(
        encoding=to_encoding(pb.framing),
        data=pb.data,
        downlink_frequency_hz=pb.downlink_frequency_hz or None,
        first_byte_at=to_dt(pb.time_first_byte_received),
        last_byte_at=to_dt(pb.time_last_byte_received),
        frame_header=pb.frame_header or None,
    )


def to_tle(pb: orbit.Tle) -> TleSet:
    return TleSet(line1=pb.line_1, line2=pb.line_2)


def from_tle(tle: TleSet) -> orbit.Tle:
    return orbit.Tle(line_1=tle.line1, line_2=tle.line2)