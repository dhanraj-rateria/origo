"""Tests for origo_info_adapter.dockerlink — the mocked RF/StellarStation hop.

Field-validated once already: this exact adapter is what carried the real
KEY_EXCHANGE traffic in the live Docker device-loop run (the "kex.ct_uplinked" log
line) — so the DownlinkFrame/CommandAck construction below is known to match the
real dataclasses, not a guess. These tests pin that behavior down so a future change
to either side gets caught here instead of three containers deep in a live run.
"""

from __future__ import annotations

import httpx
import pytest

from origo_info_adapter.dockerlink.adapter import DockerLinkAdapter
from origo_info_adapter.errors import AdapterUnavailable
from origo_info_adapter.models import ChannelSetRef, ContactPriority, SatelliteRef

BASE_URL = "http://space-mock:8080"


@pytest.fixture()
def adapter() -> DockerLinkAdapter:
    return DockerLinkAdapter(base_url=BASE_URL)


class TestHealth:
    async def test_health_true_on_200(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/health").mock(return_value=httpx.Response(200))
        assert await adapter.health() is True

    async def test_health_false_on_error_status(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/health").mock(return_value=httpx.Response(500))
        assert await adapter.health() is False

    async def test_health_false_on_connection_error(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/health").mock(side_effect=httpx.ConnectError("refused"))
        assert await adapter.health() is False


class TestFrames:
    async def test_falls_back_to_key_exchange_when_nothing_staged(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/downlink/data/status").mock(
            return_value=httpx.Response(200, json={"chunks_queued": 0}),
        )
        envelope = b"\x01\x02\x03\x04"
        respx_mock.post(f"{BASE_URL}/downlink/trigger").mock(
            return_value=httpx.Response(200, json={"device_id": "sn-001", "envelope_hex": envelope.hex()}),
        )
        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            frames = [f async for f in link.frames()]
        assert len(frames) == 1
        assert frames[0].data == envelope

    async def test_status_check_failure_falls_back_to_key_exchange_too(self, adapter, respx_mock):
        # A broken/unreachable status endpoint shouldn't take out KEY_EXCHANGE with
        # it — chunks_queued defaults to 0 on any status-check error.
        respx_mock.get(f"{BASE_URL}/downlink/data/status").mock(return_value=httpx.Response(500))
        envelope = b"\xaa\xbb"
        respx_mock.post(f"{BASE_URL}/downlink/trigger").mock(
            return_value=httpx.Response(200, json={"device_id": "sn-001", "envelope_hex": envelope.hex()}),
        )
        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            frames = [f async for f in link.frames()]
        assert len(frames) == 1
        assert frames[0].data == envelope

    async def test_yields_nothing_on_trigger_http_error(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/downlink/data/status").mock(
            return_value=httpx.Response(200, json={"chunks_queued": 0}),
        )
        respx_mock.post(f"{BASE_URL}/downlink/trigger").mock(return_value=httpx.Response(500))
        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            frames = [f async for f in link.frames()]
        assert frames == []

    async def test_yields_nothing_on_trigger_connection_error(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/downlink/data/status").mock(
            return_value=httpx.Response(200, json={"chunks_queued": 0}),
        )
        respx_mock.post(f"{BASE_URL}/downlink/trigger").mock(side_effect=httpx.ConnectError("refused"))
        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            frames = [f async for f in link.frames()]
        assert frames == []

    async def test_drains_staged_data_as_raw_ciphertext_frames(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/downlink/data/status").mock(
            return_value=httpx.Response(200, json={"chunks_queued": 3}),
        )
        chunks = [b"\x01\x02", b"\x03\x04", b"\x05\x06"]
        route = respx_mock.post(f"{BASE_URL}/downlink/data")
        route.side_effect = [
            httpx.Response(200, json={"sequence_number": 0, "ciphertext_hex": chunks[0].hex(), "remaining": 2}),
            httpx.Response(200, json={"sequence_number": 1, "ciphertext_hex": chunks[1].hex(), "remaining": 1}),
            httpx.Response(200, json={"sequence_number": 2, "ciphertext_hex": chunks[2].hex(), "remaining": 0}),
            httpx.Response(404),
        ]

        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            frames = [f async for f in link.frames()]

        # Raw ciphertext, no magic/seq wrapper — pass_executor._run_data_delivery
        # tracks its own sequence number and would fail to authenticate anything
        # with extra bytes glued on. See origo_space.server's module docstring.
        assert [f.data for f in frames] == chunks

    async def test_data_drain_stops_cleanly_on_http_error_mid_stream(self, adapter, respx_mock):
        respx_mock.get(f"{BASE_URL}/downlink/data/status").mock(
            return_value=httpx.Response(200, json={"chunks_queued": 2}),
        )
        route = respx_mock.post(f"{BASE_URL}/downlink/data")
        route.side_effect = [
            httpx.Response(200, json={"sequence_number": 0, "ciphertext_hex": "aabb", "remaining": 1}),
            httpx.Response(500),
        ]
        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            frames = [f async for f in link.frames()]
        assert len(frames) == 1   # got the first chunk, then stopped instead of raising


class TestSendCommands:
    async def test_hex_encodes_the_command_and_returns_ack(self, adapter, respx_mock):
        route = respx_mock.post(f"{BASE_URL}/uplink").mock(return_value=httpx.Response(200))
        ct_envelope = b"\xaa\xbb\xcc"

        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            ack = await link.send_commands(
                [ct_envelope], channel_set_ref=ChannelSetRef("cs-s-band"), request_id="req-1",
            )

        assert route.called
        import json

        sent = json.loads(route.calls.last.request.content)
        assert sent == {"envelope_hex": ct_envelope.hex()}
        assert ack.request_id == "req-1"

    async def test_raises_adapter_unavailable_on_http_error(self, adapter, respx_mock):
        respx_mock.post(f"{BASE_URL}/uplink").mock(return_value=httpx.Response(503))
        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            with pytest.raises(AdapterUnavailable):
                await link.send_commands([b"\x00"], channel_set_ref=ChannelSetRef("cs-s-band"))

    async def test_defaults_request_id_when_not_given(self, adapter, respx_mock):
        respx_mock.post(f"{BASE_URL}/uplink").mock(return_value=httpx.Response(200))
        async with adapter.open_link(satellite_ref=SatelliteRef("sn-001")) as link:
            ack = await link.send_commands([b"\x00"], channel_set_ref=ChannelSetRef("cs-s-band"))
        assert ack.request_id  # non-empty, don't pin the exact default string


class TestUnsupportedSurface:
    """No booking model for a direct container-to-container link — see the module
    docstring in adapter.py. Pinning this down so it stays a deliberate choice, not
    an accidental regression the next time this file is touched."""

    async def test_list_contact_windows_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError):
            await adapter.list_contact_windows(satellite_ref=SatelliteRef("sn-001"))

    async def test_reserve_contact_not_implemented(self, adapter):
        with pytest.raises(NotImplementedError):
            await adapter.reserve_contact(reservation_token="tok", priority=ContactPriority.MEDIUM)

    async def test_list_contacts_returns_empty(self, adapter):
        import datetime

        now = datetime.datetime.now(datetime.UTC)
        assert await adapter.list_contacts(
            satellite_ref=SatelliteRef("sn-001"), aos_after=now, aos_before=now,
        ) == []

    async def test_get_ephemeris_returns_none(self, adapter):
        assert await adapter.get_ephemeris(satellite_ref=SatelliteRef("sn-001")) is None