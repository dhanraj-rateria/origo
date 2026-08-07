from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...repositories.key import KeyRepository
from ..deps import get_key_repo

router = APIRouter(prefix="/v1", tags=["keys"])


@router.get("/keys")
async def list_keys(keys: Annotated[KeyRepository, Depends(get_key_repo)]) -> list[dict[str, object]]:
    return [
        {
            "id": str(k.id), "satellite_device_id": str(k.satellite_device_id),
            "ground_device_id": str(k.ground_device_id), "parameter_set": k.kem_param_set.value,
            "state": k.state.value, "created": k.created_at.isoformat(),
        }
        for k in await keys.list()
    ]