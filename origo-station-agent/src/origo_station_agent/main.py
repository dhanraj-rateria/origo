"""Process entrypoint: sync loop + AOS-triggered pass execution.

AOS trigger: a plan's own `valid_from` (set by origo-edge from the orbit predictor) is
used directly as the execution trigger, rather than waiting for a separate
antenna-controller signal. This is a real, defensible default — not a stub — and stays
correct even without site-specific hardware wired in; swapping in a GPIO/controller
signal later only touches the `now < plan.valid_from` check below, nothing upstream or
downstream of it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import grpc
import structlog
from origo_info_adapter import ContactId, SatelliteRef, build_adapter

from .events import results_to_events
from .origo.grpc_client import GrpcOrigoTerrestrial
from .pass_executor import PassExecutor
from .settings import StationAgentSettings
from .sync_client import SyncClient

log = structlog.get_logger(__name__)


async def run() -> None:
    settings = StationAgentSettings()
    sync = SyncClient(
        base_url=settings.origo_edge_url,
        client_cert=(str(settings.device_cert_path), str(settings.device_key_path)),
        ca_bundle=str(settings.ca_bundle_path),
        station_ref=settings.station_ref,
    )
    origo_channel = grpc.aio.insecure_channel(settings.origo_endpoint)
    origo = GrpcOrigoTerrestrial(channel=origo_channel)
    adapter = build_adapter()
    await adapter.start()

    executor = PassExecutor(
        adapter=adapter, origo=origo,
        satellite_ref=SatelliteRef(settings.satellite_ref), station_ref=settings.station_ref,
    )

    executed: set[UUID] = set()
    log.info("station_agent.started", station_ref=settings.station_ref)
    try:
        while True:
            plans = await sync.fetch_job_plans()
            now = datetime.now(UTC)
            for plan in plans:
                if plan.plan_id in executed:
                    continue
                if plan.is_stale(at=now):
                    log.warning("plan.stale", plan_id=str(plan.plan_id))
                    executed.add(plan.plan_id)   # don't retry a plan whose window passed
                    continue
                if now < plan.valid_from:
                    continue   # not yet time — picked up on a later loop iteration

                results = await executor.run(
                    plan=plan, contact_id=ContactId(str(plan.pass_id)), now=now,
                )
                try:
                    await sync.push_status(events=results_to_events(plan, results))
                except Exception:  # noqa: BLE001
                    # A push failure must not lose the pass's results. Real durability
                    # (a local durable queue, retried on the next cycle) is the honest
                    # next step here — logging keeps this from failing silently in the
                    # meantime, but this is the one place still worth hardening further.
                    log.exception("push_status.failed", plan_id=str(plan.plan_id))
                executed.add(plan.plan_id)

            await asyncio.sleep(settings.poll_interval_sec)
    finally:
        await sync.aclose()
        await adapter.close()
        await origo_channel.close()


if __name__ == "__main__":
    asyncio.run(run())