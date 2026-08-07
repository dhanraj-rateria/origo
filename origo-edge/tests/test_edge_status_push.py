import base64
import pytest


@pytest.mark.asyncio
async def test_push_status_activates_key_and_stores_result(client):
    sat = (await client.post("/v1/devices", json={"name": "Aster-1", "type": "ORIGO_SPACE", "serial_number": "SN-P1"})).json()["id"]
    gnd = (await client.post("/v1/devices", json={"name": "GS-North", "type": "ORIGO_TERRESTRIAL", "serial_number": "SN-P2"})).json()["id"]
    job = (await client.post("/v1/jobs", json={
        "type": "KEY_EXCHANGE", "satellite_device_id": sat, "ground_device_id": gnd, "kem_param_set": "ML_KEM_1024",
    })).json()

    push = await client.post(
        "/v1/edge/stations/SN-P2/status",
        headers={"Authorization": "Bearer test-token"},
        json={"events": [{
            "event_type": "job.result", "job_id": job["id"], "step_id": "s1", "pass_id": "p1",
            "outcome": "ACTIVE", "detail": {"key_id": "hsm-key-99"},
        }]},
    )
    assert push.status_code == 204

    updated = (await client.get(f"/v1/jobs/{job['id']}")).json()
    assert updated["state"] == "active"

    keys = (await client.get("/v1/keys")).json()
    assert any(k["id"] == job["key_id"] and k["state"] == "active" for k in keys)


@pytest.mark.asyncio
async def test_push_status_stores_data_delivery_result(client):
    sat = (await client.post("/v1/devices", json={"name": "Aster-2", "type": "ORIGO_SPACE", "serial_number": "SN-P3"})).json()["id"]
    gnd = (await client.post("/v1/devices", json={"name": "GS-South", "type": "ORIGO_TERRESTRIAL", "serial_number": "SN-P4"})).json()["id"]
    job = (await client.post("/v1/jobs", json={"type": "DATA_DELIVERY", "satellite_device_id": sat, "ground_device_id": gnd})).json()

    payload_b64 = base64.b64encode(b"decrypted-telemetry-bytes").decode()
    await client.post(
        "/v1/edge/stations/SN-P4/status", headers={"Authorization": "Bearer test-token"},
        json={"events": [{
            "event_type": "job.result", "job_id": job["id"], "step_id": "s1", "pass_id": "p1",
            "outcome": "ACTIVE", "detail": {"plaintext_b64": payload_b64, "frame_count": 3},
        }]},
    )

    result = await client.get(f"/v1/jobs/{job['id']}/result")
    assert result.status_code == 200
    assert result.content == b"decrypted-telemetry-bytes"