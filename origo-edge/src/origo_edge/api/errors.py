"""Application error envelope."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..domain.errors import ApprovalRequired, DomainError, IllegalTransition, NotFound, PolicyViolation


def _envelope(*, status_code: int, code: str, message: str, request_id: str, extra: dict[str, object] | None = None) -> JSONResponse:
    body = {"code": code, "message": message, "request_id": request_id}
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content={"error": body}, headers={"X-Request-ID": request_id})


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound) -> JSONResponse:
        return _envelope(status_code=status.HTTP_404_NOT_FOUND, code=exc.code, message=str(exc), request_id="-" )

    @app.exception_handler(IllegalTransition)
    async def _illegal(request: Request, exc: IllegalTransition) -> JSONResponse:
        return _envelope(status_code=status.HTTP_409_CONFLICT, code=exc.code, message=str(exc), request_id="-", extra={"current_state": exc.current, "attempted_state": exc.attempted, "allowed": sorted(exc.allowed)})

    @app.exception_handler(ApprovalRequired)
    async def _approval(request: Request, exc: ApprovalRequired) -> JSONResponse:
        return _envelope(status_code=status.HTTP_202_ACCEPTED, code=exc.code, message=str(exc), request_id="-", extra={"approval_request_id": str(exc.request_id), "required_approvals": exc.required})

    @app.exception_handler(PolicyViolation)
    async def _policy(request: Request, exc: PolicyViolation) -> JSONResponse:
        return _envelope(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, code=exc.code, message=str(exc), request_id="-")

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return _envelope(status_code=status.HTTP_400_BAD_REQUEST, code=exc.code, message=str(exc), request_id="-")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, code="VALIDATION_ERROR", message="Request validation failed", request_id="-", extra={"fields": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]})

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        return _envelope(status_code=exc.status_code, code=getattr(exc, "error_code", None) or f"HTTP_{exc.status_code}", message=str(exc.detail), request_id="-")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return _envelope(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, code="INTERNAL_ERROR", message="An internal error occurred. Reference the request_id when reporting.", request_id="-")
