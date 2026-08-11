"""Tests for DeviceProvisioner.

Mocks two boundaries: the `docker` SDK client (module-level `docker`/`NotFound`/
`DockerException` names in device_provisioner.py, monkeypatched directly rather than
requiring a real Docker daemon) and the httpx calls to device sidecars (via respx,
already an active plugin in this workspace). Nothing here spins up a real container —
that's what the live Docker device-loop run already proved; these tests pin down the
*sequencing* (space must exist before terrestrial; the peer-key push happens after
both identities are fetched; provisioning failures never raise past `provision()`).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from origo_edge.domain.enums import DeviceType
from origo_edge.services import device_provisioner as dp_module
from origo_edge.services.device_provisioner import DeviceProvisioner, ProvisioningError


class FakeNotFound(Exception):
    pass


class FakeSettings:
    device_provisioning_enabled = True
    docker_network = "origo-net-test"
    space_image = "origo-space:test"
    terrestrial_image = "origo-terrestrial:test"
    station_agent_image = "origo-station-agent:test"
    edge_public_url = "http://host.docker.internal:8000"


@pytest.fixture()
def fake_settings() -> FakeSettings:
    return FakeSettings()


@pytest.fixture()
def mock_docker_client(monkeypatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr(dp_module, "docker", MagicMock(from_env=lambda: client))
    monkeypatch.setattr(dp_module, "NotFound", FakeNotFound)
    monkeypatch.setattr(dp_module, "DockerException", Exception)
    client.containers.get.side_effect = FakeNotFound   # default: nothing pre-existing
    return client


def _container_with_port(host_port: str) -> MagicMock:
    container = MagicMock()
    container.attrs = {"NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": host_port}]}}}
    return container


class TestEnabled:
    def test_disabled_when_setting_is_false(self, fake_settings):
        fake_settings.device_provisioning_enabled = False
        assert DeviceProvisioner(fake_settings).enabled is False

    def test_disabled_when_docker_sdk_missing(self, fake_settings, monkeypatch):
        monkeypatch.setattr(dp_module, "docker", None)
        assert DeviceProvisioner(fake_settings).enabled is False

    def test_enabled_when_both_are_true(self, fake_settings, mock_docker_client):
        assert DeviceProvisioner(fake_settings).enabled is True

    def test_provision_is_a_noop_when_disabled(self, fake_settings, monkeypatch):
        monkeypatch.setattr(dp_module, "docker", None)
        provisioner = DeviceProvisioner(fake_settings)
        provisioner.provision(device_type=DeviceType.ORIGO_SPACE, serial_number="SN-001", peer_serial_number=None)
        # no exception is the whole test — nothing else to assert without a docker client


class TestProvisionSpace:
    def test_starts_the_container_and_waits_for_health(self, fake_settings, mock_docker_client, respx_mock):
        mock_docker_client.containers.run.return_value = _container_with_port("23456")
        respx_mock.get("http://localhost:23456/health").mock(return_value=httpx.Response(200))

        DeviceProvisioner(fake_settings).provision_space(serial_number="SN-001")

        mock_docker_client.containers.run.assert_called_once()
        kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert kwargs["name"] == "origo-space-sn-001"
        assert kwargs["environment"]["ORIGO_SPACE_DEVICE_ID"] == "SN-001"
        assert kwargs["network"] == "origo-net-test"
        assert "origo-identity-origo-space-sn-001" in kwargs["volumes"]

    def test_serial_number_is_slugified_for_the_container_name(self, fake_settings, mock_docker_client, respx_mock):
        mock_docker_client.containers.run.return_value = _container_with_port("1")
        respx_mock.get("http://localhost:1/health").mock(return_value=httpx.Response(200))

        DeviceProvisioner(fake_settings).provision_space(serial_number="SN 001/beta!")

        kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert kwargs["name"] == "origo-space-sn-001-beta"

    def test_replaces_an_existing_container_for_the_same_serial(self, fake_settings, mock_docker_client, respx_mock):
        existing = MagicMock()
        mock_docker_client.containers.get.side_effect = None
        mock_docker_client.containers.get.return_value = existing
        mock_docker_client.containers.run.return_value = _container_with_port("1")
        respx_mock.get("http://localhost:1/health").mock(return_value=httpx.Response(200))

        DeviceProvisioner(fake_settings).provision_space(serial_number="SN-001")

        existing.remove.assert_called_once_with(force=True)

    def test_raises_if_health_never_comes_up(self, fake_settings, mock_docker_client, respx_mock, monkeypatch):
        monkeypatch.setattr(dp_module.time, "sleep", lambda _: None)   # don't actually wait in tests
        mock_docker_client.containers.run.return_value = _container_with_port("1")
        respx_mock.get("http://localhost:1/health").mock(return_value=httpx.Response(503))

        with pytest.raises(ProvisioningError, match="never became healthy"):
            DeviceProvisioner(fake_settings).provision_space(serial_number="SN-001")


class TestProvisionTerrestrial:
    def test_requires_a_peer_serial_number(self, fake_settings, mock_docker_client):
        with pytest.raises(ProvisioningError, match="peer_serial_number"):
            DeviceProvisioner(fake_settings).provision_terrestrial(serial_number="SN-002", peer_serial_number="")

    def test_raises_when_peer_space_container_is_not_running(self, fake_settings, mock_docker_client):
        with pytest.raises(ProvisioningError, match="no running container"):
            DeviceProvisioner(fake_settings).provision_terrestrial(serial_number="SN-002", peer_serial_number="SN-001")

    def test_runs_the_full_ceremony_in_order(self, fake_settings, mock_docker_client, respx_mock):
        space_container = _container_with_port("10001")
        terr_container = _container_with_port("10002")

        def containers_get(name: str):
            if name == "origo-space-sn-001":
                return space_container
            raise FakeNotFound

        mock_docker_client.containers.get.side_effect = containers_get
        mock_docker_client.containers.run.return_value = terr_container

        space_pub = "aa" * 2592
        terr_pub = "bb" * 2592
        respx_mock.get("http://localhost:10001/identity").mock(
            return_value=httpx.Response(200, json={"device_id": "SN-001", "public_key_hex": space_pub}),
        )
        respx_mock.get("http://localhost:10002/health").mock(return_value=httpx.Response(200))
        respx_mock.get("http://localhost:10002/identity").mock(
            return_value=httpx.Response(200, json={"device_id": "SN-002", "public_key_hex": terr_pub}),
        )
        peer_push = respx_mock.post("http://localhost:10001/peer").mock(return_value=httpx.Response(200))

        DeviceProvisioner(fake_settings).provision_terrestrial(serial_number="SN-002", peer_serial_number="SN-001")

        # The other half of the ceremony: Space (already running) gets Terrestrial's
        # key pushed to it after Terrestrial's own identity became available.
        assert peer_push.called
        assert json.loads(peer_push.calls.last.request.content) == {"public_key_hex": terr_pub}

        # Two containers started: terrestrial, then its paired station-agent.
        assert mock_docker_client.containers.run.call_count == 2
        names = [c.kwargs["name"] for c in mock_docker_client.containers.run.call_args_list]
        assert names == ["origo-terrestrial-sn-002", "origo-station-agent-sn-002"]

        terr_kwargs = mock_docker_client.containers.run.call_args_list[0].kwargs
        assert terr_kwargs["environment"]["ORIGO_SPACE_PUBLIC_KEY_HEX"] == space_pub

        sa_kwargs = mock_docker_client.containers.run.call_args_list[1].kwargs
        assert sa_kwargs["environment"]["ORIGO_STATION_STATION_REF"] == "SN-002"
        assert sa_kwargs["environment"]["ORIGO_STATION_SATELLITE_REF"] == "SN-001"
        assert sa_kwargs["environment"]["ORIGO_RF_LINK_URL"] == "http://origo-space-sn-001:8080"


class TestProvisionDispatch:
    def test_space_device_type_calls_provision_space(self, fake_settings, mock_docker_client, respx_mock):
        mock_docker_client.containers.run.return_value = _container_with_port("1")
        respx_mock.get("http://localhost:1/health").mock(return_value=httpx.Response(200))

        DeviceProvisioner(fake_settings).provision(
            device_type=DeviceType.ORIGO_SPACE, serial_number="SN-001", peer_serial_number=None,
        )
        mock_docker_client.containers.run.assert_called_once()

    def test_failures_are_wrapped_and_reraised_not_swallowed(self, fake_settings, mock_docker_client):
        with pytest.raises(ProvisioningError):
            DeviceProvisioner(fake_settings).provision(
                device_type=DeviceType.ORIGO_TERRESTRIAL, serial_number="SN-002", peer_serial_number="SN-001",
            )


class TestDeprovision:
    def test_removes_the_space_container_only(self, fake_settings, mock_docker_client):
        space = MagicMock()
        mock_docker_client.containers.get.side_effect = None
        mock_docker_client.containers.get.return_value = space

        DeviceProvisioner(fake_settings).deprovision(serial_number="SN-001", device_type=DeviceType.ORIGO_SPACE)

        mock_docker_client.containers.get.assert_called_once_with("origo-space-sn-001")
        space.remove.assert_called_once_with(force=True)

    def test_removes_both_terrestrial_and_station_agent_containers(self, fake_settings, mock_docker_client):
        target = MagicMock()
        mock_docker_client.containers.get.side_effect = None
        mock_docker_client.containers.get.return_value = target

        DeviceProvisioner(fake_settings).deprovision(serial_number="SN-002", device_type=DeviceType.ORIGO_TERRESTRIAL)

        names = [c.args[0] for c in mock_docker_client.containers.get.call_args_list]
        assert names == ["origo-terrestrial-sn-002", "origo-station-agent-sn-002"]
        assert target.remove.call_count == 2

    def test_missing_container_is_not_an_error(self, fake_settings, mock_docker_client):
        DeviceProvisioner(fake_settings).deprovision(serial_number="SN-999", device_type=DeviceType.ORIGO_SPACE)
        # containers.get raised FakeNotFound (the fixture default) — reaching here is the assertion

    def test_noop_when_disabled(self, fake_settings, monkeypatch):
        monkeypatch.setattr(dp_module, "docker", None)
        DeviceProvisioner(fake_settings).deprovision(serial_number="SN-001", device_type=DeviceType.ORIGO_SPACE)
