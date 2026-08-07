"""Translates PassExecutor results into the wire events /v1/edge/.../status expects."""

from __future__ import annotations

import base64

from .models import JobPlan
from .pass_executor import StepResult


def results_to_events(plan: JobPlan, results: list[StepResult]) -> list[dict[str, object]]:
    events = []
    for r in results:
        detail = dict(r.detail)
        if "plaintext" in detail:
            # KB-scale payloads only. A mission producing larger data-delivery volumes
            # needs an object-store upload here instead, with a reference in the event
            # rather than the bytes themselves — not needed at this scale yet.
            detail["plaintext_b64"] = base64.b64encode(detail.pop("plaintext")).decode()
        events.append({
            "event_type": "job.result",
            "job_id": str(r.job_id),
            "step_id": str(r.step_id),
            "pass_id": str(plan.pass_id),
            "outcome": r.outcome,
            "detail": detail,
        })
    return events