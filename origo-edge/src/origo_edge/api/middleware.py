from __future__ import annotations

import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
log = structlog.get_logger(__name__)

_SILENT = {"/metrics", "/v1/health/live", "/v1/health/ready"}


def get_request_id() -> str:
    return _request_id.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id.set(rid)
        structlog.contextvars.bind_contextvars(request_id=rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            if request.url.path not in _SILENT:
                log.info("http.request", method=request.method, path=request.url.path, status=getattr(locals().get("response"), "status_code", 500), duration_ms=round(elapsed_ms, 2))
            structlog.contextvars.unbind_contextvars("request_id")
            _request_id.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
