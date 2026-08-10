"""Origo ground-network adapter.

Public surface only. Anything not re-exported here is internal and may change.
"""

from __future__ import annotations

from .errors import (
    AdapterAuthError, AdapterConfigError, AdapterError, AdapterInvalidRequest,
    AdapterQuotaExceeded, AdapterUnavailable, ContactAlreadyExecuted,
    ContactNotCancellable, ContactNotFound, ReservationTokenRejected, StreamClosed,
)
from .models import (
    Band, ChannelSetInfo, ChannelSetRef, CommandAck, Contact, ContactId, ContactOption,
    ContactPriority, ContactStatus, ContactWindow, DownlinkFrame, FrameEncoding,
    GeoPoint, ProviderId, SatelliteRef, StationInfo, StationRef, TelemetryArtifact,
    TleSet,
)
from .ports import ContactLink, GroundNetworkAdapter
from .retry import RetryPolicy

__version__ = "0.1.0"

__all__ = [  # noqa: RUF022 — grouped by concept, not alphabetised
    "GroundNetworkAdapter", "ContactLink",
    "ContactWindow", "ContactOption", "Contact", "ContactStatus", "ContactPriority",
    "ContactId", "SatelliteRef", "StationRef", "ChannelSetRef", "ProviderId",
    "StationInfo", "ChannelSetInfo", "GeoPoint", "Band",
    "DownlinkFrame", "FrameEncoding", "CommandAck", "TleSet", "TelemetryArtifact",
    "AdapterError", "AdapterConfigError", "AdapterAuthError", "AdapterInvalidRequest",
    "AdapterUnavailable", "AdapterQuotaExceeded", "ContactNotFound",
    "ContactNotCancellable", "ContactAlreadyExecuted", "ReservationTokenRejected",
    "StreamClosed", "RetryPolicy",
]


def build_adapter() -> GroundNetworkAdapter:
    """Factory driven entirely by environment.

    Imports are local so neither the fake path nor the Docker-link path ever needs
    grpc or a protobuf runtime — which is what makes the frontend, CI, and the Docker
    device loop all runnable on a machine with no StellarStation credentials and no
    generated stubs.
    """
    import os

    docker_link_url = os.environ.get("ORIGO_RF_LINK_URL")
    if docker_link_url:
        # The Docker device loop's mock RF/StellarStation hop — see dockerlink/adapter.py.
        # Checked first and unconditionally: a station-agent container provisioned for
        # the device loop has no StellarStation credentials to validate below.
        from .dockerlink.adapter import DockerLinkAdapter

        return DockerLinkAdapter(base_url=docker_link_url)

    from .stellarstation.config import StellarStationSettings

    settings = StellarStationSettings()      # validates; raises AdapterConfigError
    if not settings.enabled:
        from .fake.adapter import InMemoryAdapter

        return InMemoryAdapter()

    from .stellarstation.adapter import StellarStationAdapter

    return StellarStationAdapter(settings)
