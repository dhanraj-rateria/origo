from __future__ import annotations

from .enums import JobState as J
from .transitions import StateMachine

JOB_MACHINE: StateMachine[J] = StateMachine(
    name="job",
    initial=J.SCHEDULED,
    transitions={
        J.SCHEDULED: frozenset({J.DISPATCHED, J.FAILED}),
        J.DISPATCHED: frozenset({J.EK_SENT, J.FAILED, J.TIMED_OUT}),
        J.EK_SENT: frozenset({J.CT_RECEIVED, J.FAILED, J.TIMED_OUT}),
        J.CT_RECEIVED: frozenset({J.ACTIVE, J.FAILED, J.TIMED_OUT}),
        J.ACTIVE: frozenset(),
        J.FAILED: frozenset(),
        J.TIMED_OUT: frozenset(),
    },
)

RESCHEDULABLE = frozenset({J.FAILED, J.TIMED_OUT})
