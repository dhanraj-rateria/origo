"""Error taxonomy, mirroring origo_info_adapter's shape so callers branch on meaning."""

from __future__ import annotations


class StationAgentError(Exception):
    retryable: bool = False
    code: str = "STATION_AGENT_ERROR"

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.__cause__ = cause


class ConfigError(StationAgentError):
    code = "CONFIG_ERROR"


class JobPlanSignatureInvalid(StationAgentError):
    """Never execute a plan that fails this check."""
    code = "JOBPLAN_SIGNATURE_INVALID"


class JobPlanStale(StationAgentError):
    code = "JOBPLAN_STALE"


class OrigoUnavailable(StationAgentError):
    code = "ORIGO_UNAVAILABLE"
    retryable = True


class OrigoRejected(StationAgentError):
    """The Origo Terresitrial service refused the operation: bad signature, replay, unknown key id. Not
    retryable — retrying the same bytes will fail the same way."""
    code = "ORIGO_REJECTED"


class SyncUnavailable(StationAgentError):
    code = "SYNC_UNAVAILABLE"
    retryable = True