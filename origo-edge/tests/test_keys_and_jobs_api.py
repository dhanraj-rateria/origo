# origo-edge/tests/test_keys_and_jobs_api.py
import pytest


async def _register(client, name, type_, serial):
    resp = await client.post("/v1/devices", json={"name": name, "type": type_, "serial_number": serial})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_full_key_exchange_flow_reaches_job_plan(client):
    sat = await _register(client, "Aster-1", "ORIGO_SPACE", "SN-SAT-1")
    gnd = await _register(client, "GS-North", "ORIGO_TERRESTRIAL", "SN-GND-1")

    created = await client.post("/v1/jobs", json={
        "type": "KEY_EXCHANGE", "satellite_device_id": sat, "ground_device_id": gnd,
        "kem_param_set": "ML_KEM_1024",
    })
    assert created.status_code == 202
    job_id = created.json()["id"]

    keys = (await client.get("/v1/keys")).json()
    assert any(k["state"] == "pending_keygen" for k in keys)

    plans = await client.get(
        "/v1/edge/stations/SN-GND-1/job-plans", headers={"Authorization": "Bearer test-token"},
    )
    assert plans.status_code == 200
    steps = plans.json()["items"][0]["steps"]
    assert steps[0]["job_id"] == job_id


@pytest.mark.asyncio
async def test_wrong_device_type_rejected(client):
    sat_a = await _register(client, "Aster-1", "ORIGO_SPACE", "SN-A")
    sat_b = await _register(client, "Aster-2", "ORIGO_SPACE", "SN-B")   # both satellites — invalid pair
    resp = await client.post("/v1/jobs", json={
        "type": "KEY_EXCHANGE", "satellite_device_id": sat_a, "ground_device_id": sat_b,
        "kem_param_set": "ML_KEM_1024",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_redundant_in_flight_exchange_rejected(client):
    sat = await _register(client, "Aster-1", "ORIGO_SPACE", "SN-X")
    gnd = await _register(client, "GS-North", "ORIGO_TERRESTRIAL", "SN-Y")
    body = {"type": "KEY_EXCHANGE", "satellite_device_id": sat, "ground_device_id": gnd, "kem_param_set": "ML_KEM_1024"}
    first = await client.post("/v1/jobs", json=body)
    assert first.status_code == 202
    second = await client.post("/v1/jobs", json=body)
    assert second.status_code == 400   # PolicyViolation: already in flight


@pytest.mark.asyncio
async def test_edge_routes_reject_missing_token(client):
    resp = await client.get("/v1/edge/stations/whatever/job-plans")
    assert resp.status_code == 401