# origo-info-adapter/tests/test_adapter_reserve.py
from __future__ import annotations

import grpc
import pytest

from origo_info_adapter.errors import ReservationTokenRejected
from origo_info_adapter.models import ContactPriority

from .conftest import make_pass


@pytest.mark.asyncio
async def test_successful_reserve(adapter, fake_service):
    fake_service.passes.append(make_pass(token="tok-1"))
    windows = await adapter.list_contact_windows(satellite_ref="aster-1")
    assert len(windows) == 1
    option = windows[0].options[0]

    contact = await adapter.reserve_contact(reservation_token=option.reservation_token)
    assert contact.station.station_ref == "gs-north"
    assert fake_service.reserve_calls == 1


@pytest.mark.asyncio
async def test_failed_precondition_maps_to_rejected(adapter, fake_service):
    fake_service.reserve_error = grpc.StatusCode.FAILED_PRECONDITION
    with pytest.raises(ReservationTokenRejected):
        await adapter.reserve_contact(reservation_token="whatever")


@pytest.mark.asyncio
async def test_reused_token_rejected(adapter, fake_service):
    fake_service.passes.append(make_pass(token="tok-reuse"))
    windows = await adapter.list_contact_windows(satellite_ref="aster-1")
    token = windows[0].options[0].reservation_token
    await adapter.reserve_contact(reservation_token=token)
    with pytest.raises(ReservationTokenRejected):
        await adapter.reserve_contact(reservation_token=token)


@pytest.mark.asyncio
async def test_unavailable_on_reserve_does_not_retry(adapter, fake_service):
    """The whole point of NO_RETRY: exactly one call reaches the server."""
    fake_service.reserve_error = grpc.StatusCode.UNAVAILABLE
    with pytest.raises(Exception):  # AdapterUnavailable — see retry.py's NO_RETRY policy
        await adapter.reserve_contact(reservation_token="whatever", priority=ContactPriority.HIGH)
    assert fake_service.reserve_calls == 1


@pytest.mark.asyncio
async def test_unavailable_on_read_does_retry(adapter, fake_service, monkeypatch):
    """list_contact_windows uses the default RetryPolicy (4 attempts) — reads are safe."""
    calls = {"n": 0}
    original = fake_service._list_upcoming_available_passes

    async def flaky(request, context):
        calls["n"] += 1
        if calls["n"] < 2:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "flaky")
        return await original(request, context)

    monkeypatch.setattr(fake_service,"_list_upcoming_available_passes",flaky,)
    fake_service.passes.append(make_pass())
    windows = await adapter.list_contact_windows(satellite_ref="aster-1")
    assert len(windows) == 1
    assert calls["n"] == 2