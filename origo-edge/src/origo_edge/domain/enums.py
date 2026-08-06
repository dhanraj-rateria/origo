from __future__ import annotations

from enum import StrEnum


class DeviceType(StrEnum):
    SATELLITE_MODULE = "SATELLITE_MODULE"
    GROUND_HSM = "GROUND_HSM"


class DeviceStatus(StrEnum):
    PROVISIONED = "PROVISIONED"
    ACTIVE = "ACTIVE"
    DECOMMISSIONED = "DECOMMISSIONED"


class KemParamSet(StrEnum):
    ML_KEM_512 = "ML_KEM_512"
    ML_KEM_768 = "ML_KEM_768"
    ML_KEM_1024 = "ML_KEM_1024"

    @property
    def ek_bytes(self) -> int:
        return {"ML_KEM_512": 800, "ML_KEM_768": 1184, "ML_KEM_1024": 1568}[self.value]

    @property
    def ct_bytes(self) -> int:
        return {"ML_KEM_512": 768, "ML_KEM_768": 1088, "ML_KEM_1024": 1568}[self.value]

    @property
    def nist_category(self) -> int:
        return {"ML_KEM_512": 1, "ML_KEM_768": 3, "ML_KEM_1024": 5}[self.value]


class KeyState(StrEnum):
    PENDING_KEYGEN = "PENDING_KEYGEN"
    EK_SENT = "EK_SENT"
    AWAITING_CT = "AWAITING_CT"
    DECAPS_COMPLETE = "DECAPS_COMPLETE"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"
    DESTROYED = "DESTROYED"


class JobType(StrEnum):
    KEY_EXCHANGE = "KEY_EXCHANGE"
    DATA_DELIVERY = "DATA_DELIVERY"
    CONFIG_PUSH = "CONFIG_PUSH"
    SELF_TEST = "SELF_TEST"


class JobState(StrEnum):
    SCHEDULED = "SCHEDULED"
    DISPATCHED = "DISPATCHED"
    EK_SENT = "EK_SENT"
    CT_RECEIVED = "CT_RECEIVED"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class PassState(StrEnum):
    PREDICTED = "PREDICTED"
    RESERVATION_PENDING = "RESERVATION_PENDING"
    RESERVED = "RESERVED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RekeyTrigger(StrEnum):
    TIME_BASED = "TIME_BASED"
    PASS_BASED = "PASS_BASED"
    VOLUME_BASED = "VOLUME_BASED"
    ON_DEMAND = "ON_DEMAND"


class MetricType(StrEnum):
    TAMPER_FLAG = "TAMPER_FLAG"
    TEMP = "TEMP"
    ENTROPY_HEALTH = "ENTROPY_HEALTH"
    ERROR_COUNT = "ERROR_COUNT"
    KEY_INVENTORY = "KEY_INVENTORY"
    SELF_TEST_RESULT = "SELF_TEST_RESULT"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Role(StrEnum):
    OPERATOR = "OPERATOR"
    SECURITY_OFFICER = "SECURITY_OFFICER"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"
