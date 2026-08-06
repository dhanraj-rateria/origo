"""Authenticated grpc.aio channel construction."""

from __future__ import annotations

import grpc
import structlog
from google.auth import jwt as google_auth_jwt
from google.auth.transport.grpc import AuthMetadataPlugin
from google.auth.transport.requests import Request

from ..errors import AdapterConfigError
from .config import MAX_MESSAGE_BYTES, StellarStationSettings

log = structlog.get_logger(__name__)

_CHANNEL_OPTIONS: list[tuple[str, int]] = [
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
    # A satellite stream is idle between bursts; without keepalive, NATs and LBs
    # silently drop it and you find out at AOS.
    ("grpc.keepalive_time_ms", 30_000),
    ("grpc.keepalive_timeout_ms", 10_000),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.max_pings_without_data", 0),
    ("grpc.enable_retries", 0),   # we own retry policy; see retry.py
]


def build_channel(settings: StellarStationSettings) -> grpc.aio.Channel:
    if settings.insecure:
        log.warning("stellarstation.insecure_channel", endpoint=settings.endpoint)
        return grpc.aio.insecure_channel(settings.endpoint, options=_CHANNEL_OPTIONS)
    return grpc.aio.secure_channel(
        settings.endpoint, _build_credentials(settings), options=_CHANNEL_OPTIONS
    )


def _build_credentials(settings: StellarStationSettings) -> grpc.ChannelCredentials:
    """Self-signed JWT credentials, per-RPC, over TLS.

    `OnDemandCredentials` mints a short-lived JWT signed with the service-account key
    *locally* — there is no token-endpoint round trip. That matters for the aio path:
    AuthMetadataPlugin is invoked on a gRPC thread and would block it, but a local RSA
    signature is microseconds, so this is safe. Do not swap in credentials that fetch
    tokens over the network without moving to an async plugin.
    """
    if settings.api_key_path is None:
        raise AdapterConfigError("api_key_path is required for authenticated channels")

    try:
        signer = google_auth_jwt.Credentials.from_service_account_file(
            str(settings.api_key_path),
            audience=settings.audience,
            token_lifetime=settings.token_lifetime_sec,
        )
    except (ValueError, KeyError) as exc:
        raise AdapterConfigError(
            f"Malformed StellarStation API key at {settings.api_key_path}: {exc}"
        ) from exc

    on_demand = google_auth_jwt.OnDemandCredentials.from_signing_credentials(signer)
    plugin = AuthMetadataPlugin(on_demand, Request())
    return grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(), grpc.metadata_call_credentials(plugin)
    )