"""Key lifecycle state machine."""

from __future__ import annotations

from .enums import KeyState as K
from .transitions import StateMachine

KEY_MACHINE: StateMachine[K] = StateMachine(
    name="key",
    initial=K.PENDING_KEYGEN,
    transitions={
        K.PENDING_KEYGEN: frozenset({K.EK_SENT, K.REVOKED}),
        K.EK_SENT: frozenset({K.AWAITING_CT, K.REVOKED}),
        K.AWAITING_CT: frozenset({K.DECAPS_COMPLETE, K.REVOKED}),
        K.DECAPS_COMPLETE: frozenset({K.ACTIVE, K.REVOKED}),
        K.ACTIVE: frozenset({K.SUPERSEDED, K.REVOKED}),
        K.SUPERSEDED: frozenset({K.DESTROYED}),
        K.REVOKED: frozenset({K.DESTROYED}),
        K.DESTROYED: frozenset(),
    },
)

ACTIVE_STATES = frozenset({K.ACTIVE})
IN_FLIGHT_STATES = frozenset(
    {K.PENDING_KEYGEN, K.EK_SENT, K.AWAITING_CT, K.DECAPS_COMPLETE}
)
RETIRED_STATES = frozenset({K.SUPERSEDED, K.REVOKED, K.DESTROYED})


def requires_dual_control(target: K) -> bool:
    return target in {K.REVOKED, K.DESTROYED}
