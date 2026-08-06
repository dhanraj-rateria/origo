"""Adapter error taxonomy.

Callers must be able to branch on *meaning* without importing grpc. A worker deciding
whether to retry, park, or escalate should not be reading gRPC status codes.
"""

from __future__ import annotations


class AdapterError(Exception):
    """Base. `retryable` drives the worker's decision, not the caller's guesswork."""

    retryable: bool = False
    code: str = "ADAPTER_ERROR"

    def __init__(self, message: str, *, provider: str | None = None, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.__cause__ = cause

    def __str__(self) -> str:
        prefix = f"[{self.provider}] " if self.provider else ""
        return f"{prefix}{self.code}: {self.message}"


class AdapterConfigError(AdapterError):
    """Missing/invalid credentials or endpoint. Never retry — fix the deployment."""

    code = "ADAPTER_CONFIG_ERROR"


class AdapterAuthError(AdapterError):
    """UNAUTHENTICATED / PERMISSION_DENIED. Key expired, revoked, or wrong audience."""

    code = "ADAPTER_AUTH_ERROR"


class AdapterInvalidRequest(AdapterError):
    """INVALID_ARGUMENT. A bug in Origo or stale provider IDs. Do not retry."""

    code = "ADAPTER_INVALID_REQUEST"


class ContactNotFound(AdapterError):
    code = "CONTACT_NOT_FOUND"


class ContactNotCancellable(AdapterError):
    """FAILED_PRECONDITION — already cancelled, or inside the 10-minute pre-AOS lockout."""

    code = "CONTACT_NOT_CANCELLABLE"


class ContactAlreadyExecuted(AdapterError):
    """OUT_OF_RANGE — ongoing or finished; cancellation is meaningless."""

    code = "CONTACT_ALREADY_EXECUTED"


class ReservationTokenRejected(AdapterError):
    """The token was consumed, expired, or the option is no longer available.

    Recovery is to re-list windows and pick again — never to retry the same token.
    """

    code = "RESERVATION_TOKEN_REJECTED"


class AdapterQuotaExceeded(AdapterError):
    """RESOURCE_EXHAUSTED. Also raised if a message exceeded the 10 MB gRPC limit."""

    code = "ADAPTER_QUOTA_EXCEEDED"
    retryable = True


class AdapterUnavailable(AdapterError):
    """UNAVAILABLE / DEADLINE_EXCEEDED / ABORTED. Transient; safe to retry reads."""

    code = "ADAPTER_UNAVAILABLE"
    retryable = True


class StreamClosed(AdapterError):
    """The satellite stream ended. `recoverable` means resume via stream_id + ack_id."""

    code = "STREAM_CLOSED"

    def __init__(self, message: str, *, recoverable: bool = False, **kw: object) -> None:
        super().__init__(message, **kw)  # type: ignore[arg-type]
        self.recoverable = recoverable
        self.retryable = recoverable