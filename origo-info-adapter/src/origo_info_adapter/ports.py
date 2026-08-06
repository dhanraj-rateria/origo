"""The GroundNetworkAdapter port.

Everything in Origo that needs antenna time depends on *this*, never on a concrete
provider. Adding KSAT means adding one implementation and one config block.

Runtime-checkable Protocols rather than ABCs: implementations (including test fakes)
should not have to inherit from us.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol, runtime_checkable

from .models import (
    ChannelSetRef, CommandAck, Contact, ContactId, ContactPriority, ContactWindow,
    DownlinkFrame, ProviderId, SatelliteRef, TleSet,
)


@runtime_checkable
class ContactLink(Protocol):
    """A live bidirectional byte pipe to a satellite during a contact.

    Held open by the Edge Agent's Pass Executor for the duration of a pass (design
    §3.3.1). Async context manager: exit closes the stream and flushes acks.

    Design mapping: `frames()` carries the signed `ek` (§5.2 step 4);
    `send_commands()` carries the signed `ct` (§5.2 step 6). Neither direction is
    interpreted here — opaque bytes in, opaque bytes out, which is precisely what §3.1
    means by an untrusted bent-pipe relay.
    """

    @property
    def stream_id(self) -> str | None:
        """Provider stream id, available after the first response. Needed to resume."""

    @property
    def last_ack_id(self) -> str | None:
        """Last acknowledged message id. With stream_id, resumes without data loss."""

    async def __aenter__(self) -> ContactLink: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def frames(self) -> AsyncIterator[DownlinkFrame]:
        """Yield downlink frames until LOS or close. Acks automatically when flow
        control is enabled, so the caller cannot forget and silently lose recovery."""

    async def send_commands(
        self,
        commands: Sequence[bytes],
        *,
        channel_set_ref: ChannelSetRef,
        request_id: str | None = None,
    ) -> CommandAck:
        """Uplink a burst. Returns when the provider confirms it left the station.

        A burst, not one command per call: one RPC message can carry many commands, and
        an ML-KEM-1024 `ct` plus an ML-DSA-87 signature is a few KB across several
        frames. Sending them as one burst keeps them contiguous on the uplink.
        """

    async def close(self) -> None: ...


@runtime_checkable
class GroundNetworkAdapter(Protocol):
    """One implementation per ground-network provider."""

    @property
    def provider(self) -> ProviderId: ...

    # --- lifecycle -------------------------------------------------------------
    async def start(self) -> None:
        """Open the channel. Called once at process start; must be idempotent."""

    async def close(self) -> None: ...

    async def health(self) -> bool:
        """Cheap liveness probe. Backs /healthz — must not book anything."""

    # --- discovery -------------------------------------------------------------
    async def list_contact_windows(
        self, *, satellite_ref: SatelliteRef
    ) -> list[ContactWindow]:
        """Bookable opportunities. Options carry single-use reservation tokens whose
        lifetime is this call's result — reserve promptly or re-list."""

    # --- booking ---------------------------------------------------------------
    async def reserve_contact(
        self,
        *,
        reservation_token: str,
        priority: ContactPriority = ContactPriority.MEDIUM,
    ) -> Contact:
        """Book one ContactOption.

        NOT idempotent and NOT safely retryable — see retry.py. On an ambiguous
        failure, reconcile with list_contacts(); never resend the token.
        """

    async def cancel_contact(self, *, contact_id: ContactId) -> None:
        """Raises ContactNotCancellable inside the provider's pre-AOS lockout, and
        ContactAlreadyExecuted once it is ongoing or complete."""

    # --- observation -----------------------------------------------------------
    async def list_contacts(
        self,
        *,
        satellite_ref: SatelliteRef,
        aos_after: datetime,
        aos_before: datetime,
    ) -> list[Contact]:
        """Booked contacts in a window. Providers cap the span (StellarStation: 31
        days); implementations must chunk internally rather than surfacing the cap."""

    async def get_contact(
        self, *, satellite_ref: SatelliteRef, contact_id: ContactId
    ) -> Contact | None: ...

    async def tag_contact(
        self, *, contact_id: ContactId, tags: Mapping[str, Sequence[str]]
    ) -> None:
        """Write Origo identifiers onto the provider's own record.

        Small action, large payoff: stamping `origo_pass_id` here makes reconciliation
        an exact key lookup instead of fuzzy AOS-time matching, which is the usual
        source of duplicate-booking bugs in multi-provider schedulers. Implementations
        without this capability should no-op rather than raise.
        """

    # --- ephemeris -------------------------------------------------------------
    async def push_ephemeris(self, *, satellite_ref: SatelliteRef, tle: TleSet) -> None: ...

    async def get_ephemeris(self, *, satellite_ref: SatelliteRef) -> TleSet | None: ...

    # --- live pass -------------------------------------------------------------
    def open_link(
        self,
        *,
        satellite_ref: SatelliteRef,
        contact_id: ContactId | None = None,
        station_ref: str | None = None,
        resume_stream_id: str | None = None,
        resume_after_ack_id: str | None = None,
    ) -> ContactLink:
        """Construct a link. Not async — the stream opens on `__aenter__`, so the
        caller controls exactly when the RPC starts (which matters at AOS)."""