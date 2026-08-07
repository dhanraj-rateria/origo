from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORIGO_", env_file=".env", extra="ignore", frozen=True
    )

    env: Literal["local", "dev", "staging", "prod"] = "local"
    debug: bool = False
    service_name: str = "origo-edge"

    database_url: PostgresDsn = PostgresDsn("postgresql://postgres:postgres@localhost:5432/origo")
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_echo: bool = False

    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")

    cors_origins: tuple[str, ...] = ()
    api_root_path: str = ""

    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    auth_disabled: bool = False

    signing_key_uri: str | None = None

    default_kem_param_set: Literal["ML_KEM_512", "ML_KEM_768", "ML_KEM_1024"] = "ML_KEM_1024"
    prediction_horizon_hours: int = Field(default=72, ge=1, le=24 * 31)
    min_pass_elevation_deg: float = Field(default=10.0, ge=0, le=90)
    jobplan_lead_time_sec: int = Field(default=1800, ge=60)

    idempotency_ttl_sec: int = Field(default=24 * 3600, ge=60)
    default_page_limit: int = Field(default=50, ge=1, le=500)
    max_page_limit: int = Field(default=500, ge=1, le=1000)

    edge_device_token: str = "dev-only-change-me"

    @model_validator(mode="after")
    def _guard_production(self) -> Self:
        if self.env == "prod":
            if self.auth_disabled:
                raise ValueError("auth_disabled must be false in prod")
            if not (self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url):
                raise ValueError("OIDC configuration is required in prod")
            if not self.signing_key_uri:
                raise ValueError("signing_key_uri is required in prod")
            if self.debug or self.db_echo:
                raise ValueError("debug/db_echo must be false in prod")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
