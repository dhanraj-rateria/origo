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

    # Trust this CA for the secure channel instead of the system default trust
    # store. Added specifically for the Docker device-loop's StellarStation mock
    # (origo-stellarstation-mock): it's a real, separate container, never on
    # loopback, so `insecure=true` is correctly refused for it by
    # `_validate()` below — this is the real alternative, not a workaround for
    # that check. None (the default) means "use the system trust store," which is
    # what production must do; only ever set this for a known-fake local server.
    ca_bundle_path: Path | None = None

    # grpc's TLS hostname check validates the server's cert against the name being
    # dialed. origo-stellarstation-mock's cert is one fixed, static, shared
    # certificate (CN=origo-stellarstation-mock) baked into every instance's image —
    # it isn't reissued per container hostname (those vary per deployment:
    # origo-stellarstation-sn-002, -sn-005, ...). Set this to that fixed name to
    # match regardless of which actual hostname `endpoint` resolves. None (default)
    # performs the normal check against `endpoint` itself, which is what production
    # must do.
    tls_server_name_override: str | None = None

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
