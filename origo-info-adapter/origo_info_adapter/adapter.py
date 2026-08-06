from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import grpc
    from google.auth.transport.grpc import secure_authorized_channel
    from google.auth.transport.requests import Request
    import google_auth_jwt
except ImportError:  # pragma: no cover
    grpc = None
    secure_authorized_channel = None
    Request = None
    google_auth_jwt = None

try:
    import stellarstation_pb2
    import stellarstation_pb2_grpc
except ImportError:  # pragma: no cover
    stellarstation_pb2 = None
    stellarstation_pb2_grpc = None


@dataclass
class StellarStationJobPayload:
    job_id: str
    job_type: str
    satellite: str
    ground_station: str
    reservation_token: str
    pass_window: str
    parameter_set: str | None
    priority: str | None
    metadata: dict[str, Any]


class InfoAdapter:
    """Maps Origo Edge payloads to Infostellar StellarStation API shapes."""

    def __init__(self) -> None:
        self.service_account_file = os.environ.get(
            "STELLARSTATION_SERVICE_ACCOUNT_FILE",
            str(Path.cwd() / "stellarstation-service-account.json"),
        )
        self.endpoint = os.environ.get("STELLARSTATION_ENDPOINT", "api.stellarstation.com:443")
        self.audience = os.environ.get("STELLARSTATION_AUDIENCE", "https://api.stellarstation.com")
        self.client = self._build_client()

    def _build_client(self) -> Any:
        if not grpc or not google_auth_jwt or not secure_authorized_channel or not Request:
            return None

        if not Path(self.service_account_file).exists():
            return None

        if stellarstation_pb2_grpc is None:
            return None

        credentials = google_auth_jwt.Credentials.from_service_account_file(
            self.service_account_file,
            audience=self.audience,
        )
        jwt_creds = google_auth_jwt.OnDemandCredentials.from_signing_credentials(credentials)
        channel = secure_authorized_channel(jwt_creds, None, self.endpoint)
        return stellarstation_pb2_grpc.StellarStationServiceStub(channel)

    def is_configured(self) -> bool:
        return self.client is not None

    def map_job_to_stellarstation(self, job: dict[str, Any]) -> StellarStationJobPayload:
        metadata = {
            "created": job.get("created"),
            "route": job.get("route"),
            "priority": job.get("priority") or ("normal" if job.get("type") == "data" else "standard"),
        }
        return StellarStationJobPayload(
            job_id=job["id"],
            job_type=job["type"],
            satellite=job["satellite"],
            ground_station=job["ground_station"],
            reservation_token=job["reservation_token"],
            pass_window=job["pass_window"],
            parameter_set=job.get("parameter_set"),
            priority=job.get("priority"),
            metadata=metadata,
        )

    def submit_job(self, payload: StellarStationJobPayload) -> dict[str, Any]:
        mapped_payload = {
            "job_id": payload.job_id,
            "job_type": payload.job_type,
            "satellite": payload.satellite,
            "ground_station": payload.ground_station,
            "reservation_token": payload.reservation_token,
            "pass_window": payload.pass_window,
            "parameter_set": payload.parameter_set,
            "priority": payload.priority,
            "metadata": payload.metadata,
        }

        if self.client is None:
            return {
                "ok": False,
                "reason": "StellarStation gRPC client is not configured or dependencies are missing.",
                "payload": mapped_payload,
            }

        if not hasattr(self.client, "ReservePass"):
            return {
                "ok": False,
                "reason": "StellarStation client does not expose a ReservePass method. Ensure the installed StellarStation protobuf package matches the API.",
                "payload": mapped_payload,
            }

        request = self._build_reserve_pass_request(payload)
        response = self.client.ReservePass(request)
        return {
            "ok": True,
            "response": self._serialize_message(response),
            "payload": mapped_payload,
        }

    def _build_reserve_pass_request(self, payload: StellarStationJobPayload) -> Any:
        if stellarstation_pb2 is None:
            raise RuntimeError("StellarStation protobuf package not available")

        if not hasattr(stellarstation_pb2, "ReservePassRequest"):
            raise RuntimeError("StellarStation protobuf package is missing ReservePassRequest")

        priority_map = {
            "Low": getattr(stellarstation_pb2.Priority, "LOW", 0),
            "Normal": getattr(stellarstation_pb2.Priority, "MEDIUM", 1),
            "High": getattr(stellarstation_pb2.Priority, "HIGH", 2),
        }
        priority_value = priority_map.get(payload.priority or "Normal", getattr(stellarstation_pb2.Priority, "MEDIUM", 1))

        request = stellarstation_pb2.ReservePassRequest(
            reservation_token=payload.reservation_token,
            priority=priority_value,
        )

        return request

    def _serialize_message(self, message: Any) -> dict[str, Any]:
        if hasattr(message, "__dict__"):
            return {k: v for k, v in message.__dict__.items() if not k.startswith("_")}

        try:
            from google.protobuf.json_format import MessageToDict

            return MessageToDict(message, preserving_proto_field_name=True)
        except Exception:
            return {"repr": repr(message)}

    def map_pass_to_origo(self, raw_pass: dict[str, Any]) -> dict[str, Any]:
        return {
            "satellite": raw_pass.get("satellite") or raw_pass.get("satellite_name") or raw_pass.get("satelliteId"),
            "ground_station": raw_pass.get("ground_station") or raw_pass.get("ground_station_name") or raw_pass.get("groundStationId"),
            "band": raw_pass.get("band") or raw_pass.get("frequency_band") or "unknown",
            "aos": raw_pass.get("aos") or raw_pass.get("start_time") or raw_pass.get("startUtc"),
            "los": raw_pass.get("los") or raw_pass.get("end_time") or raw_pass.get("endUtc"),
            "elevation": raw_pass.get("elevation") or raw_pass.get("max_elevation") or "N/A",
        }

    def map_device_from_stellarstation(self, raw_device: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": raw_device.get("name") or raw_device.get("device_name") or raw_device.get("satellite_name"),
            "id": raw_device.get("id") or raw_device.get("device_id") or raw_device.get("satellite_id"),
            "type": raw_device.get("type") or raw_device.get("device_type") or "unknown",
            "mission": raw_device.get("mission") or raw_device.get("operator") or "unknown",
            "status": raw_device.get("status") or raw_device.get("state") or "unknown",
            "last_contact": raw_device.get("last_contact") or raw_device.get("last_seen") or raw_device.get("last_heartbeat"),
        }
