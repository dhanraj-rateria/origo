"""Time is injectable. Tests must never sleep or depend on wall-clock."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Test double. Advance explicitly."""

    __slots__ = ("_now",)

    def __init__(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("FrozenClock requires an aware datetime")
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now += timedelta(seconds=seconds)


def utcnow() -> datetime:
    """Module-level convenience. Prefer an injected Clock in anything testable."""
    return datetime.now(UTC)