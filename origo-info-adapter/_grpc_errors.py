from __future__ import annotations

import grpc

from .errors import (
    AdapterAuthError, AdapterError, AdapterInvalidRequest, AdapterQuotaExceeded,
    AdapterUnavailable, ContactAlreadyExecuted, ContactNotCancellable, ContactNotFound,
)

_MAP: dict[grpc.StatusCode, type[AdapterError]] = {
    grpc.StatusCode.INVALID_ARGUMENT: AdapterInvalidRequest,
    grpc.StatusCode.NOT_FOUND: ContactNotFound,
    grpc.StatusCode.FAILED_PRECONDITION: ContactNotCancellable,
    grpc.StatusCode.OUT_OF_RANGE: ContactAlreadyExecuted,
    grpc.StatusCode.UNAUTHENTICATED: AdapterAuthError,
    grpc.StatusCode.PERMISSION_DENIED: AdapterAuthError,
    grpc.StatusCode.RESOURCE_EXHAUSTED: AdapterQuotaExceeded,
    grpc.StatusCode.UNAVAILABLE: AdapterUnavailable,
    grpc.StatusCode.DEADLINE_EXCEEDED: AdapterUnavailable,
    grpc.StatusCode.ABORTED: AdapterUnavailable,
}


def translate(exc: grpc.aio.AioRpcError, *, provider: str, op: str) -> AdapterError:
    """Map a gRPC failure onto the adapter taxonomy.

    `op` is included in the message because a bare "NOT_FOUND" in a log is close to
    useless when six RPCs can produce it.
    """
    cls = _MAP.get(exc.code(), AdapterError)
    detail = (exc.details() or "").strip() or exc.code().name
    return cls(f"{op} failed: {detail}", provider=provider, cause=exc)