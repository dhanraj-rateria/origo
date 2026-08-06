"""A fake StellarStationService, served in-process over an insecure aio channel.

~80 lines buys you real gRPC semantics — status codes, streaming, deadlines — without
credentials or network. This is the highest-value test asset in the repo.
"""

from __future__ import annotations

import grpc
from grpc import aio

from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2 as ss
from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2_grpc as g


class FakeService(g.StellarStationServiceServicer):
    def __init__(self) -> None:
        self.passes: list[ss.Pass] = []
        self.plans: dict[str, ss.Plan] = {}
        self.consumed_tokens: set[str] = set()
        self.reserve_error: grpc.StatusCode | None = None

    async def ListUpcomingAvailablePasses(self, request, context):  # noqa: N802, ANN001
        if not request.satellite_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "satellite_id required")
        resp = ss.ListUpcomingAvailablePassesResponse()
        getattr(resp, "pass").extend(self.passes)
        return resp

    async def ReservePass(self, request, context):  # noqa: N802, ANN001
        if self.reserve_error is not None:
            await context.abort(self.reserve_error, "injected")
        if request.reservation_token in self.consumed_tokens:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "token consumed")
        self.consumed_tokens.add(request.reservation_token)
        plan = ss.Plan(id=f"plan-{len(self.plans) + 1}", status=ss.Plan.Status.RESERVED,
                       priority=request.priority)
        self.plans[plan.id] = plan
        return ss.ReservePassResponse(plan=plan)

    async def ListPlans(self, request, context):  # noqa: N802, ANN001
        return ss.ListPlansResponse(plan=list(self.plans.values()))

    async def CancelPlan(self, request, context):  # noqa: N802, ANN001
        if request.plan_id not in self.plans:
            await context.abort(grpc.StatusCode.NOT_FOUND, "no such plan")
        del self.plans[request.plan_id]
        return ss.CancelPlanResponse()