"""Process entrypoint: sync loop + AOS-triggered pass execution."""

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

    # Same-hardware link to Origo Terrestrial: insecure_channel, because "insecure"
    # here means "no TLS transport", not "no protection" — a Unix socket's protection
    # is the filesystem permission on the socket file (see step-by-step §1 below), and
    # layering TLS on top of a link that never leaves the machine buys nothing but
    # certificate rotation to manage. Nothing about the KEM/HSM authentication story
    # changes: ek/ct are still signed at the application layer regardless of transport.
    origo_channel = grpc.aio.insecure_channel(settings.origo_endpoint)
    origo = GrpcOrigoTerrestrial(channel=origo_channel)
    adapter = build_adapter()
    await adapter.start()

    executor = PassExecutor(
        adapter=adapter, origo=origo,
        satellite_ref=SatelliteRef(settings.satellite_ref),
        station_ref=settings.station_ref,
    )

    log.info("station_agent.started", station_ref=settings.station_ref, origo_endpoint=settings.origo_endpoint)
    try:
        while True:
            plans = await sync.fetch_job_plans()
            for plan in plans:
                # await the plan's window (AOS trigger — deployment-specific), then:
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