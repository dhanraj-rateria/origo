from __future__ import annotations
from datetime import datetime
from typing import Protocol


class AosTrigger(Protocol):
    def is_time(self, *, plan_valid_from: datetime, now: datetime) -> bool: ...


class ValidFromTrigger:
    """The current default — real and working, not tied to hardware."""
    def is_time(self, *, plan_valid_from: datetime, now: datetime) -> bool:
        return now >= plan_valid_from


class GpioTrigger:
    """Sketch for a real antenna-controller signal — implement against your actual
    controller's interface; is_time() polling a GPIO pin state is the shape."""
    def __init__(self, pin: int) -> None:
        self._pin = pin
    def is_time(self, *, plan_valid_from: datetime, now: datetime) -> bool:
        raise NotImplementedError("wire to your antenna controller's GPIO/event API")