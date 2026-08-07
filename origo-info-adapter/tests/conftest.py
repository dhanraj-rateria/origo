# origo-info-adapter/tests/conftest.py
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import grpc
import pytest_asyncio

from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2_grpc as g
from origo_info_adapter._proto.stellarstation.api.v1.radio import radio_pb2
from origo_info_adapter.stellarstation.adapter import StellarStationAdapter
from origo_info_adapter.stellarstation.config import StellarStationSettings

from .fake_grpc.servicer import FakeService


@pytest_asyncio.fixture
async def fake_service() -> AsyncIterator[FakeService]:
    yield FakeService()


@pytest_asyncio.fixture
async def fake_server(fake_service: FakeService) -> AsyncIterator[str]:
    server = grpc.aio.server()
    g.add_StellarStationServiceServicer_to_server(fake_service, server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    try:
        yield f"localhost:{port}"
    finally:
        await server.stop(grace=0)


@pytest_asyncio.fixture
async def adapter(
    fake_server: str,
    tmp_path,
) -> AsyncIterator[StellarStationAdapter]:
    api_key = tmp_path / "fake-api-key"
    api_key.write_text("fake-key")

    settings = StellarStationSettings(
        enabled=True,
        insecure=True,
        endpoint=fake_server,
        api_key_path=str(api_key),
    )

    a = StellarStationAdapter(settings)
    await a.start()
    try:
        yield a
    finally:
        await a.close()


def make_pass(*, satellite_id: str = "aster-1", token: str | None = None):
    from google.protobuf.timestamp_pb2 import Timestamp
    from origo_info_adapter._proto.stellarstation.api.v1 import stellarstation_pb2 as ss

    aos, los = Timestamp(seconds=1_700_000_000), Timestamp(seconds=1_700_000_600)
    return ss.Pass(
        aos_time=aos, los_time=los, max_elevation_degrees=45.0,
        ground_station_id="gs-north", ground_station_latitude=78.2, ground_station_longitude=15.4,
        channel_set_token=[ss.Pass.ChannelSetToken(
            channel_set=ss.ChannelSet(id="cs-s-band", name="S-band",
                downlink=radio_pb2.RadioDeviceConfiguration(center_frequency_hz=2_250_000_000)),
            reservation_token=token or f"token-{uuid.uuid4()}", unit_price=12.5,
        )],
    )