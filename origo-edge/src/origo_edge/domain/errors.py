from __future__ import annotations

from collections.abc import Set as AbstractSet
from uuid import UUID


class DomainError(Exception):
    code = "DOMAIN_ERROR"


class NotFound(DomainError):
    code = "NOT_FOUND"

    def __init__(self, resource: str, identifier: object) -> None:
        super().__init__(f"{resource} '{identifier}' not found")
        self.code = f"{resource.upper()}_NOT_FOUND"


class IllegalTransition(DomainError):
    code = "ILLEGAL_STATE_TRANSITION"

    def __init__(
        self, *, machine: str, current: str, attempted: str, allowed: AbstractSet[str]
    ) -> None:
        super().__init__(
            f"{machine}: cannot move {current} -> {attempted}; "
            f"allowed: {sorted(allowed) or 'none (terminal)'}"
        )
        self.machine, self.current, self.attempted, self.allowed = (
            machine, current, attempted, allowed,
        )


class PolicyViolation(DomainError):
    code = "POLICY_VIOLATION"


class ApprovalRequired(DomainError):
    code = "APPROVAL_REQUIRED"

    def __init__(self, *, request_id: UUID, required: int, have: int) -> None:
        super().__init__(
            f"requires {required} approvals, has {have}; "
            f"approval request {request_id} created"
        )
        self.request_id, self.required, self.have = request_id, required, have


class AuditChainBroken(DomainError):
    code = "AUDIT_CHAIN_BROKEN"
