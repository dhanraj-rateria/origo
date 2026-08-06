"""Retry policy. Deliberately small — the important content is what is *not* retried."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import structlog

from .errors import AdapterError

T = TypeVar("T")
log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 4
    base_delay_sec: float = 0.5
    max_delay_sec: float = 8.0
    jitter: float = 0.3

    def delay_for(self, attempt: int) -> float:
        raw = min(self.base_delay_sec * (2 ** (attempt - 1)), self.max_delay_sec)
        return raw * (1.0 + random.uniform(-self.jitter, self.jitter))  # noqa: S311


NO_RETRY = RetryPolicy(attempts=1)


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    op: str,
) -> T:
    """Retry only when the raised AdapterError says it is safe.

    The decision lives on the error class, not here, so a new error type cannot be
    accidentally retried by omission — the default is `retryable = False`.
    """
    last: AdapterError | None = None
    for attempt in range(1, policy.attempts + 1):
        try:
            return await fn()
        except AdapterError as exc:
            if not exc.retryable or attempt == policy.attempts:
                raise
            last = exc
            delay = policy.delay_for(attempt)
            log.warning(
                "adapter.retry", op=op, attempt=attempt, of=policy.attempts,
                delay_sec=round(delay, 3), code=exc.code,
            )
            await asyncio.sleep(delay)
    raise last  # unreachable; satisfies the type checker