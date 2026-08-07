# origo-edge/tests/test_one_active_key.py — proves the partial index, not the service check
import asyncio
import pytest
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_only_one_concurrent_activation_wins(app, client):
    from origo_edge.db.session import get_session

    sat_resp = await client.post("/v1/devices", json={"name": "Aster-1", "type": "ORIGO_SPACE", "serial_number": "SN-C1"})
    gnd_resp = await client.post("/v1/devices", json={"name": "GS-North", "type": "ORIGO_TERRESTRIAL", "serial_number": "SN-C2"})
    sat_id, gnd_id = sat_resp.json()["id"], gnd_resp.json()["id"]

    sessionmaker = app.state.sessionmaker
    from origo_edge.db.models.key import Key
    from origo_edge.domain.enums import KemParamSet, KeyState

    async def insert_active() -> bool:
        try:
            async with sessionmaker() as session, session.begin():
                session.add(Key(
                    satellite_device_id=sat_id, ground_device_id=gnd_id,
                    kem_param_set=KemParamSet.ML_KEM_1024, state=KeyState.ACTIVE,
                ))
            return True
        except IntegrityError:
            return False

    results = await asyncio.gather(insert_active(), insert_active(), return_exceptions=False)
    assert sorted(results) == [False, True]