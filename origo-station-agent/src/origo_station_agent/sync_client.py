"""Talks to origo-edge (design §3.3.1's Sync Client) — the only component in this
process that touches the network toward the Platform. Everything else here talks
locally, to the Origo Terrestrial or to origo_info_adapter.

Authenticates with mTLS using this station's own device credential: the
same client-certificate identity origo-edge's api/security.py already claims to support
for device auth, distinct from the OIDC path human dashboard users take. See the
origo-edge additions below for the route this calls.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .errors import SyncUnavailable
from .models import JobPlan

log = structlog.get_logger(__name__)


class SyncClient:
    def __init__(
        self, *, base_url: str, client_cert: tuple[str, str], ca_bundle: str,
        station_ref: str, timeout_sec: float = 15.0,
    ) -> None:
        self._station_ref = station_ref
        self._client = httpx.AsyncClient(
            base_url=base_url, cert=client_cert, verify=ca_bundle,
            timeout=timeout_sec, http2=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(SyncUnavailable),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, max=8),
        reraise=True,
    )
    async def fetch_job_plans(self, *, since: datetime | None = None) -> list[JobPlan]:
        """Idempotent GET — safe to retry freely, unlike anything in
        origo_info_adapter that touches billable antenna time."""
        try:
            resp = await self._client.get(
                f"/v1/edge/stations/{self._station_ref}/job-plans",
                params={"since": since.isoformat()} if since else None,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise SyncUnavailable(f"fetch_job_plans failed: {exc}", cause=exc) from exc
        return [JobPlan.model_validate(item) for item in resp.json()["items"]]

    async def push_status(self, *, events: list[dict[str, object]]) -> None:
        """Batch telemetry/audit/job-status upload, called from the sync loop between
        passes (main.py) — never from inside pass_executor.py while a pass is live."""
        try:
            resp = await self._client.post(
                f"/v1/edge/stations/{self._station_ref}/status", json={"events": events},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("sync.push_failed", error=str(exc), count=len(events))
            raise SyncUnavailable(f"push_status failed: {exc}", cause=exc) from exc
