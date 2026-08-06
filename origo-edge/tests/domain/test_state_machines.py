import pytest

from origo_edge.domain.enums import JobState, KeyState
from origo_edge.domain.errors import IllegalTransition
from origo_edge.domain.job_lifecycle import JOB_MACHINE
from origo_edge.domain.key_lifecycle import KEY_MACHINE


def test_every_key_state_is_reachable() -> None:
    assert KEY_MACHINE.reachable() == frozenset(KeyState)


def test_every_job_state_is_reachable() -> None:
    assert JOB_MACHINE.reachable() == frozenset(JobState)


def test_destroyed_is_terminal() -> None:
    assert KEY_MACHINE.is_terminal(KeyState.DESTROYED)


@pytest.mark.parametrize(
    "current,target",
    [
        (KeyState.PENDING_KEYGEN, KeyState.ACTIVE),
        (KeyState.DESTROYED, KeyState.ACTIVE),
        (KeyState.SUPERSEDED, KeyState.ACTIVE),
        (KeyState.ACTIVE, KeyState.EK_SENT),
    ],
)
def test_illegal_transitions_raise(current: KeyState, target: KeyState) -> None:
    with pytest.raises(IllegalTransition) as exc:
        KEY_MACHINE.transition(current=current, target=target)
    assert exc.value.allowed is not None


def test_terminal_job_states_are_not_reopenable() -> None:
    for terminal in (JobState.ACTIVE, JobState.FAILED, JobState.TIMED_OUT):
        assert JOB_MACHINE.is_terminal(terminal)
