from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..errors import AdapterConfigError

MAX_MESSAGE_BYTES = 10 * 1024 * 1024   # StellarStation supports 10 MB; gRPC defaults to 4


class StellarStationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORIGO_STELLARSTATION_", extra="ignore", frozen=True
    )

    enabled: bool = False
    api_key_path: Path | None = None

    # host:port for gRPC. QA: stream.qa.stellarstation.com:443
    endpoint: str = "api.stellarstation.com:443"

    # JWT `aud`. Must match what the server expects, and is NOT always the same string
    # as `endpoint` — a mismatch surfaces as UNAUTHENTICATED, which is the single most
    # common first-run failure. Keep them separately configurable.
    audience: str = "https://api.stellarstation.com"

    token_lifetime_sec: int = Field(default=60, ge=30, le=3600)
    default_timeout_sec: float = Field(default=30.0, gt=0)
    reserve_timeout_sec: float = Field(default=60.0, gt=0)

    # Bidi stream tuning
    enable_flow_control: bool = True
    enable_stream_events: bool = True
    stream_reconnect_attempts: int = Field(default=3, ge=0)

    insecure: bool = False   # local fake server only; refuses non-loopback endpoints

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.enabled:
            return self
        if self.api_key_path is None:
            raise AdapterConfigError(
                "ORIGO_STELLARSTATION_ENABLED=true but ORIGO_STELLARSTATION_API_KEY_PATH "
                "is unset. Set enabled=false to use the in-memory fake."
            )
        if not self.api_key_path.is_file():
            raise AdapterConfigError(f"API key file not found: {self.api_key_path}")
        if self.insecure and not self._is_loopback():
            raise AdapterConfigError(
                f"insecure=true is only permitted for loopback endpoints, got {self.endpoint}"
            )
        return self

    def _is_loopback(self) -> bool:
        host = self.endpoint.rsplit(":", 1)[0]
        return host in {"localhost", "127.0.0.1", "::1", "[::1]"}