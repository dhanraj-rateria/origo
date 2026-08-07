# origo-edge/tests/test_devices_api.py
import pytest


@pytest.mark.asyncio
async def test_register_and_list_device(client):
    resp = await client.post("/v1/devices", json={"name": "Aster-1", "type": "ORIGO_SPACE", "serial_number": "SN-001"})
    assert resp.status_code == 201

    listed = await client.get("/v1/devices")
    assert listed.status_code == 200
    assert any(d["name"] == "Aster-1" for d in listed.json())


@pytest.mark.asyncio
async def test_duplicate_serial_rejected(client):
    body = {"name": "GS-North", "type": "ORIGO_TERRESTRIAL", "serial_number": "SN-DUP"}
    first = await client.post("/v1/devices", json=body)
    assert first.status_code == 201
    second = await client.post("/v1/devices", json=body)
    assert second.status_code == 409