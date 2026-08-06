import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# allow importing the sibling origo-info-adapter package
ROOT_DIR = Path(__file__).resolve().parent.parent
ADAPTER_DIR = ROOT_DIR.parent / "origo-info-adapter"
sys.path.insert(0, str(ADAPTER_DIR))

from origo_info_adapter.adapter import InfoAdapter

app = FastAPI(title="Origo Edge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

adapter = InfoAdapter()

class NewJobRequest(BaseModel):
    type: str
    satellite: str
    ground_station: str
    reservation_token: str
    pass_window: str
    parameter_set: str | None = None
    priority: str | None = None

class PolicyRequest(BaseModel):
    name: str
    mission: str
    trigger: str
    parameter_set: str
    parameter_value: str

class AcknowledgeRequest(BaseModel):
    acknowledged_by: str

STATE_MAP = {
    "active": "Active",
    "completed": "Completed",
    "scheduled": "Scheduled",
    "dispatched": "Dispatched",
    "failed": "Failed",
}

jobs = [
    {
        "id": "JOB-2201",
        "type": "key",
        "satellite": "Aster-1",
        "ground_station": "GS-North",
        "reservation_token": "tok-1001",
        "pass_window": "Today 14:32",
        "parameter_set": "ML-KEM-1024",
        "priority": "Normal",
        "route": "Aster-1 → GS-North",
        "state": "active",
        "created": "11m ago",
    },
    {
        "id": "JOB-2202",
        "type": "data",
        "satellite": "Aster-1",
        "ground_station": "GS-North",
        "reservation_token": "tok-1002",
        "pass_window": "Today 14:34",
        "parameter_set": "HSD-1",
        "priority": "High",
        "route": "Aster-1 → GS-North",
        "state": "completed",
        "created": "9m ago",
    },
    {
        "id": "JOB-2205",
        "type": "data",
        "satellite": "Vela-1",
        "ground_station": "GS-South",
        "reservation_token": "tok-2001",
        "pass_window": "Today 16:05",
        "parameter_set": "HSD-1",
        "priority": "Normal",
        "route": "Vela-1 → GS-South",
        "state": "dispatched",
        "created": "2m ago",
    },
    {
        "id": "JOB-2203",
        "type": "key",
        "satellite": "Vela-1",
        "ground_station": "GS-South",
        "reservation_token": "tok-3001",
        "pass_window": "Tomorrow 08:47",
        "parameter_set": "ML-KEM-1024",
        "priority": "Normal",
        "route": "Vela-1 → GS-South",
        "state": "scheduled",
        "created": "1h ago",
    },
    {
        "id": "JOB-2204",
        "type": "data",
        "satellite": "Aster-2",
        "ground_station": "GS-South",
        "reservation_token": "tok-3002",
        "pass_window": "Yesterday 09:02",
        "parameter_set": "HSD-1",
        "priority": "Normal",
        "route": "Aster-2 → GS-South",
        "state": "failed",
        "created": "1d ago",
    },
]

devices = [
    {"name": "Aster-1 module", "id": "MOD-1001", "type": "Satellite module", "mission": "Aster constellation", "status": "Active", "last_contact": "2h ago"},
    {"name": "Aster-2 module", "id": "MOD-1002", "type": "Satellite module", "mission": "Aster constellation", "status": "Active", "last_contact": "6h ago"},
    {"name": "Vela-1 module", "id": "MOD-2001", "type": "Satellite module", "mission": "Vela", "status": "Active", "last_contact": "40m ago"},
    {"name": "GS-North HSM", "id": "HSM-01", "type": "Ground HSM", "mission": "—", "status": "Active", "last_contact": "40m ago"},
    {"name": "GS-South HSM", "id": "HSM-02", "type": "Ground HSM", "mission": "—", "status": "Active", "last_contact": "1h ago"},
]

passes = [
    {
        "reservation_token": "tok-1001",
        "satellite": "Aster-1",
        "ground_station": "GS-North",
        "band": "S-band",
        "aos": "Today 14:32",
        "los": "Today 14:41",
        "elevation": "61°",
    },
    {
        "reservation_token": "tok-1002",
        "satellite": "Aster-1",
        "ground_station": "GS-North",
        "band": "X-band",
        "aos": "Today 14:34",
        "los": "Today 14:40",
        "elevation": "61°",
    },
    {
        "reservation_token": "tok-2001",
        "satellite": "Vela-1",
        "ground_station": "GS-South",
        "band": "S-band",
        "aos": "Today 16:05",
        "los": "Today 16:12",
        "elevation": "44°",
    },
    {
        "reservation_token": "tok-3001",
        "satellite": "Aster-2",
        "ground_station": "GS-South",
        "band": "Passed",
        "aos": "Yesterday 09:02",
        "los": "Yesterday 09:11",
        "elevation": "28°",
    },
]

keys = [
    {"id": "KEY-8841", "route": "Aster-1 → GS-North", "parameter_set": "ML-KEM-1024", "state": "Active", "created": "11m ago"},
    {"id": "KEY-8830", "route": "Aster-1 → GS-North", "parameter_set": "ML-KEM-1024", "state": "Superseded", "created": "1d ago"},
    {"id": "KEY-8850", "route": "Vela-1 → GS-South", "parameter_set": "ML-KEM-1024", "state": "Pending keygen", "created": "1h ago"},
]

telemetry = [
    {"name": "Aster-1 module", "temperature": "34°C", "tamper": "Clear", "self_test": "Pass"},
    {"name": "Vela-1 module", "temperature": "37°C", "tamper": "Clear", "self_test": "3 errors"},
    {"name": "GS-North HSM", "temperature": "22°C", "tamper": "Clear", "self_test": "Pass"},
]

policies = [
    {"name": "Aster constellation default", "mission": "Aster constellation", "trigger": "Pass-based", "parameter_set": "ML-KEM-1024", "value": "Every pass"},
    {"name": "Vela high-assurance", "mission": "Vela", "trigger": "Time-based", "parameter_set": "ML-KEM-1024", "value": "24h"},
]

alerts = [
    {"id": "alert-501", "severity": "Warning", "device": "Vela-1 module", "condition": "Error counter elevated", "state": "Open", "opened": "3h ago"},
    {"id": "alert-502", "severity": "Info", "device": "Aster-2 module", "condition": "Self-test completed", "state": "Resolved", "opened": "1d ago"},
]

audit = [
    {"event": "key.activated", "device": "Aster-1 module", "actor": "system", "time": "11m ago"},
    {"event": "config.pushed", "device": "Vela-1 module", "actor": "a.rao", "time": "2h ago"},
    {"event": "device.registered", "device": "GS-South HSM", "actor": "admin", "time": "2d ago"},
]

@app.get("/api/overview")
def get_overview():
    return {
        "satellites": 3,
        "ground_stations": 2,
        "active_keys": 2,
        "open_alerts": sum(1 for a in alerts if a["state"] == "Open"),
    }

@app.get("/api/devices")
def get_devices():
    return devices

@app.get("/api/passes")
def get_passes():
    return passes

@app.get("/api/jobs")
def get_jobs():
    return jobs

@app.get("/api/keys")
def get_keys():
    return keys

@app.get("/api/telemetry")
def get_telemetry():
    return telemetry

@app.get("/api/policies")
def get_policies():
    return policies

@app.get("/api/alerts")
def get_alerts():
    return alerts

@app.get("/api/audit")
def get_audit():
    return audit

@app.post("/api/jobs")
def create_job(payload: NewJobRequest):
    next_id = len(jobs) + 2206
    job_id = f"JOB-{next_id}"
    route = f"{payload.satellite} → {payload.ground_station}"
    state = "scheduled"
    new_job = {
        "id": job_id,
        "type": payload.type,
        "satellite": payload.satellite,
        "ground_station": payload.ground_station,
        "reservation_token": payload.reservation_token,
        "pass_window": payload.pass_window,
        "parameter_set": payload.parameter_set,
        "priority": payload.priority,
        "route": route,
        "state": state,
        "created": "just now",
    }
    jobs.insert(0, new_job)
    adapter_job = adapter.map_job_to_stellarstation(new_job)
    adapter_response = adapter.submit_job(adapter_job)
    new_job["adapter_response"] = adapter_response
    return new_job

@app.post("/api/policies")
def save_policy(payload: PolicyRequest):
    policy = {
        "name": payload.name,
        "mission": payload.mission,
        "trigger": payload.trigger,
        "parameter_set": payload.parameter_set,
        "value": payload.parameter_value,
    }
    policies.insert(0, policy)
    return policy

@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, payload: AcknowledgeRequest):
    for alert in alerts:
        if alert["id"] == alert_id:
            alert["state"] = "Acknowledged"
            return alert
    raise HTTPException(status_code=404, detail="Alert not found")
