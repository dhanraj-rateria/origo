from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

import grpc
import structlog

from .._grpc_errors import translate
from ..errors import AdapterConfigError, AdapterError, ReservationTokenRejected
from ..models import (
    Contact, ContactId, ContactPriority, ContactWindow, ProviderId, STELLARSTATION,
    SatelliteRef, TleSet,
)
from ..ports import ContactLink, GroundNetworkAdapter
from ..retry import NO_RETRY, RetryPolicy, with_retry
from . import mapping as m
from .._proto.stellarstation.api.v1 import stellarstation_pb2 as ss
from .._proto.stellarstation.api.v1 import stellarstation_pb2_grpc as ss_grpc
from .channel import build_channel
from .config import StellarStationSettings
from .link import StellarStationLink

log = structlog.get_logger(__name__)

# StellarStation rejects ListPlans windows longer than 31 days.
_MAX_LIST_SPAN = timedelta(days=31)


class StellarStationAdapter(GroundNetworkAdapter):
    """Infostellar StellarStation implementation of the GroundNetworkAdapter port.

    One instance per process. Owns the channel; `start()`/`close()` are lifecycle hooks
    driven by the host (FastAPI lifespan, worker startup, Edge Agent main).
    """

    def __init__(
        self,
        settings: StellarStationSettings,
        *,
        read_policy: RetryPolicy | None = None,
    ) -> None:
        if not settings.enabled:
            raise AdapterConfigError(
                "StellarStationAdapter constructed with enabled=false; "
                "use origo_info_adapter.fake.InMemoryAdapter instead"
            )
        self._settings = settings
        self._read_policy = read_policy or RetryPolicy()
        self._channel: grpc.aio.Channel | None = None
        self._stub: ss_grpc.StellarStationServiceStub | None = None

    @property
    def provider(self) -> ProviderId:
        return STELLARSTATION

    # ---------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self._channel is not None:
            return
        self._channel = build_channel(self._settings)
        self._stub = ss_grpc.StellarStationServiceStub(self._channel)
        log.info(
            "stellarstation.started",
            endpoint=self._settings.endpoint,
            audience=self._settings.audience,
        )

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close(grace=2.0)
            self._channel = None
            self._stub = None
            log.info("stellarstation.closed")

    async def health(self) -> bool:
        """Channel readiness only — deliberately makes no RPC.

        A liveness probe that called ListUpcomingAvailablePasses would burn provider
        quota on every Kubernetes probe interval.
        """
        if self._channel is None:
            return False
        try:
            await self._channel.channel_ready()
        except (grpc.aio.AioRpcError, TimeoutError):
            return False
        return True

    @property
    def _client(self) -> ss_grpc.StellarStationServiceStub:
        if self._stub is None:
            raise AdapterConfigError("adapter not started; call start() first")
        return self._stub

    # ---------------------------------------------------------------- discovery

    async def list_contact_windows(
        self, *, satellite_ref: SatelliteRef
    ) -> list[ContactWindow]:
        async def call() -> list[ContactWindow]:
            req = ss.ListUpcomingAvailablePassesRequest(satellite_id=satellite_ref)
            try:
                resp = await self._client.ListUpcomingAvailablePasses(
                    req, timeout=self._settings.default_timeout_sec
                )
            except grpc.aio.AioRpcError as exc:
                raise translate(
                    exc, provider=self.provider, op="ListUpcomingAvailablePasses"
                ) from exc
            # `pass` is a Python keyword, so the generated attribute must be reached
            # via getattr — this is the one place the proto naming leaks.
            windows = [
                m.to_contact_window(p, satellite_ref=satellite_ref)
                for p in getattr(resp, "pass")
            ]
            log.debug(
                "stellarstation.windows",
                satellite_ref=satellite_ref,
                count=len(windows),
                options=sum(len(w.options) for w in windows),
            )
            return windows

        return await with_retry(call, policy=self._read_policy, op="list_contact_windows")

    # ---------------------------------------------------------------- booking

    async def reserve_contact(
        self,
        *,
        reservation_token: str,
        priority: ContactPriority = ContactPriority.MEDIUM,
    ) -> Contact:
        req = ss.ReservePassRequest(
            reservation_token=reservation_token, priority=m.from_priority(priority)
        )
        try:
            # NO_RETRY: single-use token, billable, non-idempotent. See retry.py.
            resp = await with_retry(
                lambda: self._client.ReservePass(
                    req, timeout=self._settings.reserve_timeout_sec
                ),
                policy=NO_RETRY,
                op="reserve_contact",
            )
        except grpc.aio.AioRpcError as exc:
            err = translate(exc, provider=self.provider, op="ReservePass")
            if exc.code() in {
                grpc.StatusCode.FAILED_PRECONDITION,
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.INVALID_ARGUMENT,
            }:
                raise ReservationTokenRejected(
                    "reservation token was consumed, expired, or invalid; "
                    "re-list windows and select again",
                    provider=self.provider,
                    cause=exc,
                ) from exc
            raise err from exc

        contact = m.to_contact(resp.plan)
        # Never log the token, even truncated.
        log.info(
            "stellarstation.reserved",
            contact_id=contact.contact_id,
            satellite_ref=contact.satellite_ref,
            station_ref=contact.station.station_ref,
            aos=contact.aos.isoformat(),
            priority=priority.value,
        )
        return contact

    async def cancel_contact(self, *, contact_id: ContactId) -> None:
        try:
            await self._client.CancelPlan(
                ss.CancelPlanRequest(plan_id=contact_id),
                timeout=self._settings.default_timeout_sec,
            )
        except grpc.aio.AioRpcError as exc:
            raise translate(exc, provider=self.provider, op="CancelPlan") from exc
        log.info("stellarstation.cancelled", contact_id=contact_id)

    # ---------------------------------------------------------------- observation

    async def list_contacts(
        self,
        *,
        satellite_ref: SatelliteRef,
        aos_after: datetime,
        aos_before: datetime,
    ) -> list[Contact]:
        """Chunks internally so callers never see the provider's 31-day cap."""
        if aos_before <= aos_after:
            raise AdapterError(
                f"aos_before ({aos_before}) must be after aos_after ({aos_after})",
                provider=self.provider,
            )

        out: list[Contact] = []
        seen: set[str] = set()
        cursor = aos_after
        while cursor < aos_before:
            chunk_end = min(cursor + _MAX_LIST_SPAN, aos_before)
            for contact in await self._list_contacts_chunk(satellite_ref, cursor, chunk_end):
                if contact.contact_id not in seen:
                    seen.add(contact.contact_id)
                    out.append(contact)
            cursor = chunk_end
        out.sort(key=lambda c: c.aos)
        return out

    async def _list_contacts_chunk(
        self, satellite_ref: SatelliteRef, start: datetime, end: datetime
    ) -> list[Contact]:
        async def call() -> list[Contact]:
            req = ss.ListPlansRequest(
                satellite_id=satellite_ref,
                aos_after=m.from_dt(start),
                aos_before=m.from_dt(end),
            )
            try:
                resp = await self._client.ListPlans(
                    req, timeout=self._settings.default_timeout_sec
                )
            except grpc.aio.AioRpcError as exc:
                raise translate(exc, provider=self.provider, op="ListPlans") from exc
            return [m.to_contact(p) for p in resp.plan]

        return await with_retry(call, policy=self._read_policy, op="list_contacts")

    async def get_contact(
        self, *, satellite_ref: SatelliteRef, contact_id: ContactId
    ) -> Contact | None:
        """No GetPlan RPC exists, so this is a filtered ListPlans.

        Callers that need many contacts must use list_contacts() — calling this in a
        loop is an N-fold amplification against the provider's quota.
        """
        from ..clock import utcnow

        now = utcnow()
        contacts = await self.list_contacts(
            satellite_ref=satellite_ref,
            aos_after=now - timedelta(days=31),
            aos_before=now + timedelta(days=31),
        )
        return next((c for c in contacts if c.contact_id == contact_id), None)

    async def tag_contact(
        self, *, contact_id: ContactId, tags: Mapping[str, Sequence[str]]
    ) -> None:
        metadata = ss.PlanMetadata(
            metadata={
                k: ss.PlanMetadata.Metadata(data=list(v)) for k, v in tags.items()
            }
        )
        try:
            await self._client.SetPlanMetadata(
                ss.SetPlanMetadataRequest(plan_id=contact_id, metadata=metadata),
                timeout=self._settings.default_timeout_sec,
            )
        except grpc.aio.AioRpcError as exc:
            raise translate(exc, provider=self.provider, op="SetPlanMetadata") from exc

    # ---------------------------------------------------------------- ephemeris

    async def push_ephemeris(self, *, satellite_ref: SatelliteRef, tle: TleSet) -> None:
        try:
            await self._client.AddTle(
                ss.AddTleRequest(satellite_id=satellite_ref, tle=m.from_tle(tle)),
                timeout=self._settings.default_timeout_sec,
            )
        except grpc.aio.AioRpcError as exc:
            raise translate(exc, provider=self.provider, op="AddTle") from exc
        log.info("stellarstation.tle_pushed", satellite_ref=satellite_ref)

    async def get_ephemeris(self, *, satellite_ref: SatelliteRef) -> TleSet | None:
        try:
            resp = await self._client.GetTle(
                ss.GetTleRequest(satellite_id=satellite_ref),
                timeout=self._settings.default_timeout_sec,
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() is grpc.StatusCode.NOT_FOUND:
                return None
            raise translate(exc, provider=self.provider, op="GetTle") from exc
        return m.to_tle(resp.tle) if resp.HasField("tle") else None

    async def set_ephemeris_source_manual(self, *, satellite_ref: SatelliteRef) -> None:
        """Provider-specific extension, not on the port.

        Call this before push_ephemeris, or the provider will keep overwriting your
        uploaded TLE from NORAD. Deliberately outside GroundNetworkAdapter: it is a
        StellarStation concept, and putting it on the port would force every future
        provider to fake it.
        """
        try:
            await self._client.SetTleSource(
                ss.SetTleSourceRequest(
                    satellite_id=satellite_ref,
                    source=ss.SetTleSourceRequest.Source.MANUAL,
                ),
                timeout=self._settings.default_timeout_sec,
            )
        except grpc.aio.AioRpcError as exc:
            raise translate(exc, provider=self.provider, op="SetTleSource") from exc

    # ---------------------------------------------------------------- live pass

    def open_link(
        self,
        *,
        satellite_ref: SatelliteRef,
        contact_id: ContactId | None = None,
        station_ref: str | None = None,
        resume_stream_id: str | None = None,
        resume_after_ack_id: str | None = None,
    ) -> ContactLink:
        return StellarStationLink(
            stub=self._client,
            settings=self._settings,
            satellite_ref=satellite_ref,
            contact_id=contact_id,
            station_ref=station_ref,
            resume_stream_id=resume_stream_id,
            resume_after_ack_id=resume_after_ack_id,
        )