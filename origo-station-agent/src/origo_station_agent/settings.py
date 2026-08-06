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

    origo_endpoint: str

    poll_interval_sec: int = Field(default=60, ge=5)