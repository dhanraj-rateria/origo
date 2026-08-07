# origo-info-adapter/tests/test_integration.py
import pytest
from origo_info_adapter import build_adapter

@pytest.mark.integration
async def test_real_stellarstation_lists_windows():
    adapter = build_adapter()   # reads ORIGO_STELLARSTATION_* from the environment
    await adapter.start()
    try:
        windows = await adapter.list_contact_windows(satellite_ref="<your test satellite id>")
        assert isinstance(windows, list)   # QA sandbox may legitimately return zero
    finally:
        await adapter.close()