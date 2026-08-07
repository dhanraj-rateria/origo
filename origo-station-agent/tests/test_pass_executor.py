# origo-station-agent/tests/test_pass_executor.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from origo_info_adapter import ChannelSetRef, ContactId, SatelliteRef
from origo_info_adapter.fake.adapter import InMemoryAdapter

from origo_station_agent.errors import JobPlanStale
from origo_station_agent.models import JobPlan, JobPlanStep, JobType
from origo_station_agent.pass_executor import PassExecutor, _frame_ct

from .fake_origo import FakeOrigoTerrestrial


def make_plan(steps: list[JobPlanStep], *, valid_minutes: int = 15) -> JobPlan:
    now = datetime.now(UTC)

    if valid_minutes < 0:
        valid_from = now + timedelta(minutes=valid_minutes - 1)
        valid_until = now + timedelta(minutes=valid_minutes)
    else:
        valid_from = now - timedelta(minutes=1)
        valid_until = now + timedelta(minutes=valid_minutes)

    return JobPlan(
        plan_id=uuid.uuid4(),
        ground_station_id="gs-north",
        pass_id=uuid.uuid4(),
        valid_from=valid_from,
        valid_until=valid_until,
        steps=tuple(steps),
        signature=b"",
        signed_payload=b"",
    )

@pytest.mark.asyncio
async def test_key_exchange_step_succeeds():
    origo = FakeOrigoTerrestrial()
    adapter = InMemoryAdapter(downlink_script=[
        b"OSKX" + b"".join(  # build a minimal valid envelope inline for the test
            len(p).to_bytes(4, "big") + p for p in (b"ek-bytes", b"ek-sig", b"aster-1", b"nonce123")
        )
    ])
    executor = PassExecutor(adapter=adapter, origo=origo, satellite_ref=SatelliteRef("aster-1"), station_ref="gs-north")

    step = JobPlanStep(
        step_id=uuid.uuid4(), job_id=uuid.uuid4(), job_type=JobType.KEY_EXCHANGE,
        expected_start_offset_sec=0, timeout_sec=30, parameters={"channel_set_ref": "cs-s-band"},
    )
    results = await executor.run(plan=make_plan([step]), contact_id=ContactId("c-1"), now=datetime.now(UTC))

    assert results[0].outcome == "ACTIVE"
    assert results[0].detail["key_id"] == "key-42"
    assert len(origo.encapsulate_calls) == 1
    assert adapter.uplinked[0][1] == _frame_ct(b"ct-bytes", b"ct-sig")


@pytest.mark.asyncio
async def test_key_exchange_step_fails_on_rejection():
    origo = FakeOrigoTerrestrial()
    origo.reject_encapsulate = True
    envelope = b"OSKX" + b"".join(len(p).to_bytes(4, "big") + p for p in (b"ek", b"sig", b"aster-1", b"n"))
    adapter = InMemoryAdapter(downlink_script=[envelope])
    executor = PassExecutor(adapter=adapter, origo=origo, satellite_ref=SatelliteRef("aster-1"), station_ref="gs-north")

    step = JobPlanStep(step_id=uuid.uuid4(), job_id=uuid.uuid4(), job_type=JobType.KEY_EXCHANGE,
                        expected_start_offset_sec=0, timeout_sec=30, parameters={})
    results = await executor.run(plan=make_plan([step]), contact_id=ContactId("c-1"), now=datetime.now(UTC))

    assert results[0].outcome == "FAILED"
    assert len(adapter.uplinked) == 0   # never uplinked anything after a rejection


@pytest.mark.asyncio
async def test_data_delivery_decrypts_all_frames():
    origo = FakeOrigoTerrestrial()
    adapter = InMemoryAdapter(downlink_script=[b"cipher-0", b"cipher-1", b"cipher-2"])
    executor = PassExecutor(adapter=adapter, origo=origo, satellite_ref=SatelliteRef("aster-1"), station_ref="gs-north")

    step = JobPlanStep(step_id=uuid.uuid4(), job_id=uuid.uuid4(), job_type=JobType.DATA_DELIVERY,
                        expected_start_offset_sec=0, timeout_sec=30, parameters={"key_id": "key-42"})
    results = await executor.run(plan=make_plan([step]), contact_id=ContactId("c-1"), now=datetime.now(UTC))

    assert results[0].outcome == "ACTIVE"
    assert results[0].detail["frame_count"] == 3
    assert results[0].detail["plaintext"] == b"plaintext-cipher-0plaintext-cipher-1plaintext-cipher-2"


@pytest.mark.asyncio
async def test_data_delivery_fails_partway_reports_bytes_before_failure():
    origo = FakeOrigoTerrestrial()
    origo.reject_decrypt_after = 1
    adapter = InMemoryAdapter(downlink_script=[b"c0", b"c1-bad", b"c2"])
    executor = PassExecutor(adapter=adapter, origo=origo, satellite_ref=SatelliteRef("aster-1"), station_ref="gs-north")

    step = JobPlanStep(step_id=uuid.uuid4(), job_id=uuid.uuid4(), job_type=JobType.DATA_DELIVERY,
                        expected_start_offset_sec=0, timeout_sec=30, parameters={"key_id": "key-42"})
    results = await executor.run(plan=make_plan([step]), contact_id=ContactId("c-1"), now=datetime.now(UTC))

    assert results[0].outcome == "FAILED"
    assert results[0].detail["bytes_before_failure"] == len(b"plaintext-c0")


@pytest.mark.asyncio
async def test_stale_plan_never_opens_a_link():
    origo, adapter = FakeOrigoTerrestrial(), InMemoryAdapter()
    executor = PassExecutor(adapter=adapter, origo=origo, satellite_ref=SatelliteRef("aster-1"), station_ref="gs-north")
    stale = make_plan([], valid_minutes=-30)   # valid_until already in the past
    with pytest.raises(JobPlanStale):
        await executor.run(plan=stale, contact_id=ContactId("c-1"), now=datetime.now(UTC))
    assert adapter.uplinked == []   # the assertion that actually matters