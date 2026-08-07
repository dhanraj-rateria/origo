"""A fake StellarStationService, served in-process over an insecure aio channel."""

from __future__ import annotations

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2 as ss
from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2_grpc as g


class FakeService(g.StellarStationServiceServicer):
    def __init__(self) -> None:
        self.passes: list[ss.Pass] = []
        self.plans: dict[str, ss.Plan] = {}
        self.consumed_tokens: set[str] = set()
        self.reserve_error: grpc.StatusCode | None = None
        self.reserve_calls = 0
        self.list_windows_calls = 0

    async def ListUpcomingAvailablePasses(self, request, context):
        return await self._list_upcoming_available_passes(request, context)


    async def _list_upcoming_available_passes(self, request, context):
        response = ss.ListUpcomingAvailablePassesResponse()
        getattr(response, "pass").extend(self.passes)
        return response

    async def ReservePass(self, request, context):
        self.reserve_calls += 1
        if self.reserve_error is not None:
            await context.abort(self.reserve_error, "injected failure")
        if request.reservation_token in self.consumed_tokens:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "token already consumed")
        self.consumed_tokens.add(request.reservation_token)
        plan = ss.Plan(id=f"plan-{len(self.plans) + 1}", status=ss.Plan.Status.RESERVED, priority=request.priority, aos_time=Timestamp(seconds=1_700_000_000),
    los_time=Timestamp(seconds=1_700_000_600), ground_station_id="gs-north",
    ground_station_latitude=78.2,
    ground_station_longitude=15.4,
    max_elevation_degrees=45.0,)
        self.plans[plan.id] = plan
        return ss.ReservePassResponse(plan=plan)

    async def ListPlans(self, request, context):
        return ss.ListPlansResponse(plan=list(self.plans.values()))

    async def CancelPlan(self, request, context):
        if request.plan_id not in self.plans:
            await context.abort(grpc.StatusCode.NOT_FOUND, "no such plan")
        del self.plans[request.plan_id]
        return ss.CancelPlanResponse()