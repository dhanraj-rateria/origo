"""Local-dev device provisioning: spins up a real Docker container for a registered
device so the fleet the Platform shows actually corresponds to something running,
and automates design §9's provisioning ceremony between a newly-registered Origo
Terrestrial and the Origo Space device it's paired with.

Scope, deliberately: this is a local-dev/demo convenience, not a fleet-management
system. RF/StellarStation are represented by origo-stellarstation-mock — a real,
separate container implementing the real stellarstation.proto contract — not by this
process calling Origo Space directly. As of this version, this class no longer talks
to any Origo Space container's HTTP surface at all: every identity/peer/health call
that used to go straight to Origo Space is relayed through the mock's admin API
instead, and the operational crypto path (origo-station-agent's real
StellarStationAdapter, against the mock) never touches this class at all.

Ordering constraint, matching the real trust model (no live channel to negotiate a
peer key after the fact — see §2): an Origo Terrestrial device's peer_serial_number
must name an already-registered, already-running Origo Space device. Origo Space
always comes first. See docs/docker-device-loop.md.
"""

from __future__ import annotations

import re
import time

import httpx
import structlog

try:
    import docker
    from docker.errors import DockerException, NotFound
except ImportError:  # docker SDK is an optional dependency of a dev-only feature
    docker = None  # type: ignore[assignment]
    DockerException = NotFound = Exception  # type: ignore[assignment,misc]

from ..domain.enums import DeviceType
from ..settings import Settings

log = structlog.get_logger(__name__)

_NAME_RE = re.compile(r"[^a-z0-9-]")


class ProvisioningError(RuntimeError):
    pass


def _container_name(prefix: str, serial_number: str) -> str:
    slug = _NAME_RE.sub("-", serial_number.lower()).strip("-") or "device"
    return f"origo-{prefix}-{slug}"


class DeviceProvisioner:
    """One instance per origo-edge process, held on app.state (see main.py). Talks to
    the *local* Docker daemon (`docker.from_env()`) — this process still runs directly
    on the host exactly as `make dev-edge` always has; it just also holds the keys to
    the host's Docker socket."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = docker.from_env() if (docker is not None and settings.device_provisioning_enabled) else None
        self._http = httpx.Client(timeout=15.0)

    @property
    def enabled(self) -> bool:
        return self._settings.device_provisioning_enabled and self._client is not None

    # ------------------------------------------------------------------ plumbing --

    def _ensure_network(self) -> None:
        assert self._client is not None
        try:
            self._client.networks.get(self._settings.docker_network)
        except NotFound:
            self._client.networks.create(self._settings.docker_network, driver="bridge")

    def _run(
        self, *, image: str, name: str, environment: dict[str, str],
        ports: dict[str, object] | None = None, volumes: dict[str, dict[str, str]] | None = None,
    ):
        assert self._client is not None
        try:
            self._client.containers.get(name).remove(force=True)   # re-registering the same serial replaces its container
        except NotFound:
            pass
        return self._client.containers.run(
            image, name=name, detach=True, environment=environment,
            network=self._settings.docker_network, ports=ports or {}, volumes=volumes or {},
            extra_hosts={"host.docker.internal": "host-gateway"},
            restart_policy={"Name": "unless-stopped"},
        )

    def _published_port(self, container, container_port: str, *, retries: int = 20, delay_sec: float = 0.5) -> int:
        for _ in range(retries):
            container.reload()
            bindings = container.attrs["NetworkSettings"]["Ports"].get(container_port)
            if bindings:
                return int(bindings[0]["HostPort"])
            time.sleep(delay_sec)
        raise ProvisioningError(f"container {container.name} never published {container_port}")

    def _wait_healthy(self, base_url: str, *, path: str = "/health", retries: int = 30, delay_sec: float = 0.5) -> None:
        for _ in range(retries):
            try:
                if self._http.get(f"{base_url}{path}").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(delay_sec)
        raise ProvisioningError(f"{base_url} never became healthy")

    # -------------------------------------------------------------- provisioning --

    def provision_space(self, *, serial_number: str) -> None:
        """Unchanged by the StellarStation-mock rework: this is a provisioner
        checking that the container it *just started* actually came up — not a
        third party talking to Origo Space operationally. That distinction is what
        the mock exists to enforce for everything that happens *after* this point,
        not for this initial self-check."""
        self._ensure_network()
        name = _container_name("space", serial_number)
        container = self._run(
            image=self._settings.space_image, name=name,
            environment={
                "ORIGO_SPACE_DEVICE_ID": serial_number,
                "ORIGO_SPACE_IDENTITY_PATH": "/data/identity.json",
            },
            ports={"8080/tcp": None},
            volumes={f"origo-identity-{name}": {"bind": "/data", "mode": "rw"}},
        )
        port = self._published_port(container, "8080/tcp")
        self._wait_healthy(f"http://localhost:{port}")
        log.info("provisioner.space_up", serial_number=serial_number, container=name, port=port)

    def provision_terrestrial(self, *, serial_number: str, peer_serial_number: str) -> None:
        assert self._client is not None
        if not peer_serial_number:
            raise ProvisioningError(
                "an Origo Terrestrial device needs peer_serial_number set to its "
                "paired Origo Space device's serial number"
            )

        self._ensure_network()
        space_name = _container_name("space", peer_serial_number)
        try:
            self._client.containers.get(space_name)   # existence check only — see below, we never touch its port directly
        except NotFound as exc:
            raise ProvisioningError(
                f"peer Origo Space device '{peer_serial_number}' has no running "
                "container — register (and let it provision) that device first"
            ) from exc
        # Reachable from other containers on origo-net by Docker DNS — never
        # published to the host, and after this point nothing in this class calls
        # it directly again either.
        space_container_url = f"http://{space_name}:8080"

        # ---- start the StellarStation mock sidecar for this pairing --------------
        ss_name = _container_name("stellarstation", serial_number)
        ss_container = self._run(
            image=self._settings.stellarstation_mock_image, name=ss_name,
            environment={}, ports={"8080/tcp": None},
        )
        ss_admin_port = self._published_port(ss_container, "8080/tcp")
        ss_admin_url = f"http://localhost:{ss_admin_port}"
        self._wait_healthy(ss_admin_url)

        # The mock's only source of truth for which container a satellite_id
        # actually relates to.
        reg = self._http.post(
            f"{ss_admin_url}/admin/satellites/{peer_serial_number}",
            json={"space_url": space_container_url},
        )
        reg.raise_for_status()

        # ---- provisioning ceremony, relayed through the mock, not direct ----------
        space_identity = self._http.get(f"{ss_admin_url}/admin/satellites/{peer_serial_number}/identity")
        space_identity.raise_for_status()

        terr_name = _container_name("terrestrial", serial_number)
        terr_container = self._run(
            image=self._settings.terrestrial_image, name=terr_name,
            environment={
                "ORIGO_TERRESTRIAL_DEVICE_ID": serial_number,
                "ORIGO_TERRESTRIAL_IDENTITY_PATH": "/data/identity.json",
                "ORIGO_TERRESTRIAL_GRPC_ADDR": "0.0.0.0:50051",
                "ORIGO_SPACE_PUBLIC_KEY_HEX": space_identity.json()["public_key_hex"],
            },
            ports={"8080/tcp": None},
            volumes={f"origo-identity-{terr_name}": {"bind": "/data", "mode": "rw"}},
        )
        terr_port = self._published_port(terr_container, "8080/tcp")
        terr_url = f"http://localhost:{terr_port}"
        self._wait_healthy(terr_url)
        terr_identity = self._http.get(f"{terr_url}/identity")
        terr_identity.raise_for_status()

        # The other half of the ceremony: Origo Space was already running when this
        # Origo Terrestrial was created, so it never received the peer key at
        # startup — push it now, through the mock, the same way everything else
        # reaches Origo Space from this point on.
        peer_push = self._http.post(
            f"{ss_admin_url}/admin/satellites/{peer_serial_number}/peer",
            json={"public_key_hex": terr_identity.json()["public_key_hex"]},
        )
        peer_push.raise_for_status()

        sa_name = _container_name("station-agent", serial_number)
        self._run(
            image=self._settings.station_agent_image, name=sa_name,
            environment={
                "ORIGO_STATION_STATION_REF": serial_number,
                "ORIGO_STATION_SATELLITE_REF": peer_serial_number,
                "ORIGO_STATION_ORIGO_EDGE_URL": self._settings.edge_public_url,
                "ORIGO_STATION_ORIGO_ENDPOINT": f"{terr_name}:50051",
                # This is the whole swap: point the real StellarStationAdapter at
                # the mock instead of setting ORIGO_RF_LINK_URL. build_adapter()
                # needs no changes — StellarStationSettings().enabled being true is
                # already what selects the real adapter; API key path, CA bundle,
                # server-name override, and insecure=false are baked into the
                # image's defaults (see that Dockerfile), since they're the same
                # for every station-agent instance.
                "ORIGO_STELLARSTATION_ENABLED": "true",
                "ORIGO_STELLARSTATION_ENDPOINT": f"{ss_name}:50052",
            },
        )
        log.info(
            "provisioner.terrestrial_up", serial_number=serial_number,
            peer=peer_serial_number, container=terr_name, station_agent=sa_name, stellarstation_mock=ss_name,
        )

    def deprovision(self, *, serial_number: str, device_type: DeviceType) -> None:
        if not self.enabled:
            return
        assert self._client is not None
        if device_type is DeviceType.ORIGO_SPACE:
            names = [_container_name("space", serial_number)]
        else:
            names = [
                _container_name("terrestrial", serial_number),
                _container_name("station-agent", serial_number),
                _container_name("stellarstation", serial_number),
            ]
        for name in names:
            try:
                self._client.containers.get(name).remove(force=True)
            except NotFound:
                pass

    def provision(self, *, device_type: DeviceType, serial_number: str, peer_serial_number: str | None) -> None:
        """Best-effort: a provisioning failure must never fail device registration —
        the Postgres row is the source of truth for the fleet; the container is a
        local-dev convenience layered on top of it. Callers (devices.py) decide how
        to surface a failure to the caller; this only logs and re-raises."""
        if not self.enabled:
            log.info("provisioner.disabled", serial_number=serial_number)
            return
        try:
            if device_type is DeviceType.ORIGO_SPACE:
                self.provision_space(serial_number=serial_number)
            else:
                self.provision_terrestrial(serial_number=serial_number, peer_serial_number=peer_serial_number or "")
        except (DockerException, ProvisioningError, httpx.HTTPError) as exc:
            log.warning("provisioner.failed", serial_number=serial_number, error=str(exc))
            raise ProvisioningError(str(exc)) from exc
