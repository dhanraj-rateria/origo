from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StationAgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORIGO_STATION_", extra="ignore", frozen=True)

    station_ref: str
    satellite_ref: str        # single-satellite deployment; a station serving several
                               # satellites needs this promoted to a list — not needed yet

    origo_edge_url: str
    device_cert_path: Path
    device_key_path: Path
    ca_bundle_path: Path

    # Same physical hardware as Origo Terrestrial: a Unix domain socket, not a network
    # endpoint. grpc-python accepts this target form natively — no separate "transport
    # kind" flag needed, the scheme in the string is enough.
    # e.g. "unix:///var/run/origo/origo-terrestrial.sock"
    origo_endpoint: str = "unix:///var/run/origo/origo-terrestrial.sock"

    poll_interval_sec: int = Field(default=60, ge=5)