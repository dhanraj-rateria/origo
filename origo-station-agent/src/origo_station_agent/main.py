"""Process entrypoint: sync loop + AOS-triggered pass execution.

AOS/LOS detection is deliberately left unimplemented here — it's genuinely
deployment-specific (a scheduler keyed off the JobPlan's own timing, an
antenna-controller signal, a GPIO edge) in a way the rest of this module isn't. This
shows the wiring; the trigger is a decision for whoever owns the physical site.
"""

from __future__ import annotations

import asyncio

import grpc
import structlog
from origo_info_adapter import SatelliteRef, build_adapter

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
    origo_channel = grpc.aio.secure_channel(settings.origo_endpoint, grpc.ssl_channel_credentials())
    origo = GrpcOrigoTerrestrial(channel=origo_channel)
    adapter = build_adapter()
    await adapter.start()

    executor = PassExecutor(
        adapter=adapter, origo=origo,
        satellite_ref=SatelliteRef(settings.satellite_ref),
        station_ref=settings.station_ref,
    )

    log.info("station_agent.started", station_ref=settings.station_ref)
    try:
        while True:
            plans = await sync.fetch_job_plans()
            for plan in plans:
                # await the plan's window (AOS trigger — see module docstring), then:
                # results = await executor.run(plan=plan, contact_id=..., now=...)
                # await sync.push_status(events=_results_to_events(plan, results))
                pass
            await asyncio.sleep(settings.poll_interval_sec)
    finally:
        await sync.aclose()
        await adapter.close()
        await origo_channel.close()


if __name__ == "__main__":
    asyncio.run(run())