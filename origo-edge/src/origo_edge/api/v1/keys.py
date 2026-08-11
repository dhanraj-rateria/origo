from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ...domain.enums import KeyState
from ...repositories.key import KeyRepository
from ...services.key_service import KeyService
from ..deps import get_key_repo, get_key_service

router = APIRouter(prefix="/v1", tags=["keys"])


@router.get("/keys")
async def list_keys(
    keys: Annotated[KeyRepository, Depends(get_key_repo)],
    revoked: bool = False,
) -> list[dict[str, object]]:
    """revoked=false (default) shows everything except REVOKED keys — SUPERSEDED and
    DESTROYED still show up here too, same as before this change; revoked=true is a
    dedicated view of exactly the keys this endpoint's own DELETE (now revoke)
    action produces. Filtered in Python rather than pushed into the repository
    query — repositories/key.py wasn't available to add a filtered list() variant
    to, and at this scale it doesn't matter."""
    all_keys = await keys.list()
    filtered = [k for k in all_keys if (k.state is KeyState.REVOKED) == revoked]
    return [
        {
            "id": str(k.id), "satellite_device_id": str(k.satellite_device_id),
            "ground_device_id": str(k.ground_device_id), "parameter_set": k.kem_param_set.value,
            "state": k.state.value, "created": k.created_at.isoformat(),
        }
        for k in filtered
    ]


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: uuid.UUID,
    keys: Annotated[KeyRepository, Depends(get_key_repo)],
    key_service: Annotated[KeyService, Depends(get_key_service)],
) -> None:
    """Revokes the key. Never removes the row — the ask was "set as revoked, keep in
    the table," and KEY_MACHINE already has a real, first-class REVOKED state for
    exactly this, so this rides on KeyService.advance() rather than reaching for
    DELETE FROM keys.

    Idempotent for a key that's already REVOKED or DESTROYED (no-op, not an error —
    both are terminal-ish with respect to this action). A SUPERSEDED key is
    deliberately NOT special-cased here: KEY_MACHINE only allows SUPERSEDED ->
    DESTROYED, so calling advance(target=REVOKED) against one will raise the same
    IllegalStateTransition -> 409 you've already seen for the PENDING_KEYGEN ->
    ACTIVE bug earlier this session — that mapping already works correctly, so
    there's nothing to catch or reformat here.

    NOTE: this assumes KeyRepository has a plain .get(key_id) method — only
    .get_for_update() is directly confirmed (from key_service.py's advance()). If
    this 500s with an AttributeError, that's why.
    """
    key = await keys.get(key_id)
    if key is None:
        raise HTTPException(404, detail=f"key {key_id} not found")
    if key.state in (KeyState.REVOKED, KeyState.DESTROYED):
        return
    await key_service.advance(key_id=key_id, target=KeyState.REVOKED)