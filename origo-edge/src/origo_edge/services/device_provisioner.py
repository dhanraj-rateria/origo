# services/device_provisioner.py
"""Local-dev device provisioning: spins up a real Docker container for a registered
device so the fleet the Platform shows actually corresponds to something running,
and automates design §9's provisioning ceremony (each side's identity keypair is
pre-provisioned; the peer's public key is "a config value someone copies over by
hand") between a newly-registered Origo Terrestrial and the Origo Space device it's
paired with.

Scope, deliberately: this is a local-dev/demo convenience, not a fleet-management
system, and it doesn't touch RF or StellarStation — those stay mocked (see
origo_info_adapter.dockerlink). What it does make real: an actual container boundary,
an actual container-to-container network hop, and the actual WolfCryptEngine/ML-KEM/
ML-DSA handshake code path, exercised end to end instead of only in a unit test.

Ordering constraint, matching the real trust model (no live channel to negotiate a
peer key after the fact — see §2): an Origo Terrestrial device's peer_serial_number
must name an already-registered, already-running Origo Space device. Origo Space
always comes first. See docs/docker-device-loop.md for the full walkthrough.
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
    the *local* Docker daemon (`docker.from_env()`) — this is Docker-outside-of-
    Docker: origo-edge itself keeps running directly on the host, exactly as the
    Makefile's `dev-edge` target already does; it just also holds the keys to the
    host's Docker socket."""

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
        assert self._client is not None
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
            space_container = self._client.containers.get(space_name)
        except NotFound as exc:
            raise ProvisioningError(
                f"peer Origo Space device '{peer_serial_number}' has no running "
                "container — register (and let it provision) that device first"
            ) from exc
        space_port = self._published_port(space_container, "8080/tcp")
        space_url = f"http://localhost:{space_port}"
        space_identity = self._http.get(f"{space_url}/identity")
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
        # startup — push it now. Automated equivalent of "someone copies it over by
        # hand," not a new trust decision: the provisioner is the thing that just
        # created both containers, so it is exactly the party a manual ceremony
        # would trust to relay this.
        peer_push = self._http.post(
            f"{space_url}/peer", json={"public_key_hex": terr_identity.json()["public_key_hex"]},
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
                "ORIGO_RF_LINK_URL": f"http://{space_name}:8080",
            },
        )
        log.info(
            "provisioner.terrestrial_up", serial_number=serial_number,
            peer=peer_serial_number, container=terr_name, station_agent=sa_name,
        )

    def deprovision(self, *, serial_number: str, device_type: DeviceType) -> None:
        if not self.enabled:
            return
        assert self._client is not None
        names = (
            [_container_name("space", serial_number)] if device_type is DeviceType.ORIGO_SPACE
            else [_container_name("terrestrial", serial_number), _container_name("station-agent", serial_number)]
        )
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
