"""Generic state-machine primitive."""

from __future__ import annotations

from collections.abc import Mapping, Set as AbstractSet
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from .errors import IllegalTransition

S = TypeVar("S", bound=StrEnum)


@dataclass(frozen=True, slots=True)
class StateMachine(Generic[S]):
    name: str
    initial: S
    transitions: Mapping[S, frozenset[S]]

    def allowed_from(self, state: S) -> AbstractSet[S]:
        return self.transitions.get(state, frozenset())

    def is_terminal(self, state: S) -> bool:
        return not self.allowed_from(state)

    def can(self, *, current: S, target: S) -> bool:
        return target in self.allowed_from(current)

    def transition(self, *, current: S, target: S) -> S:
        if not self.can(current=current, target=target):
            raise IllegalTransition(
                machine=self.name,
                current=current.value,
                attempted=target.value,
                allowed={s.value for s in self.allowed_from(current)},
            )
        return target

    def reachable(self) -> frozenset[S]:
        seen: set[S] = {self.initial}
        frontier = [self.initial]
        while frontier:
            for nxt in self.allowed_from(frontier.pop()):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        return frozenset(seen)
