"""Tests for origo_space.server — the FastAPI wrapper that makes Origo Space
reachable in the Docker device loop.

Deliberately does NOT import origo_terrestrial: the "terrestrial side" of the
roundtrip test is reproduced directly against origo_crypto.WolfCryptEngine (the
same three operations OrigoTerrestrialServicer.VerifyAndEncapsulate performs —
verify, encapsulate, sign), mirroring the module-independence rule the rest of this
codebase already follows (see origo_space/identity.py, origo_crypto/envelope.py).

Each test gets a freshly-reloaded server module with its own tmp_path identity
file — the module holds process-lifetime global state (_peer_public_key,
_traffic_key, _pending_chunks), which is correct for a real single-device
container but means tests need real isolation, not shared globals leaking between
them.
"""

from __future__ import annotations

import base64
import hashlib
import importlib

import pytest
from fastapi.testclient import TestClient

from origo_crypto.envelope import pack_ct_envelope, parse_ek_envelope
from origo_crypto.wolfcrypt_engine import WolfCryptEngine

HKDF_CONTEXT = b"origo-traffic-key"   # confirmed against the real terrestrial-side call, see service.py


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORIGO_SPACE_DEVICE_ID", "test-sat")
    monkeypatch.setenv("ORIGO_SPACE_IDENTITY_PATH", str(tmp_path / "identity.json"))
    from origo_space import server

    importlib.reload(server)
    return TestClient(server.app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "device_id": "test-sat"}


def test_identity_returns_a_real_ml_dsa_87_public_key(client):
    resp = client.get("/identity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_id"] == "test-sat"
    # ML-DSA-87 public key is 2592 bytes -> 5184 hex chars.
    assert len(bytes.fromhex(body["public_key_hex"])) == 2592


def test_set_peer_rejects_invalid_hex(client):
    resp = client.post("/peer", json={"public_key_hex": "not-hex"})
    assert resp.status_code == 400


def test_uplink_without_peer_key_is_409(client):
    resp = client.post("/uplink", json={"envelope_hex": "aa"})
    assert resp.status_code == 409


def test_uplink_rejects_invalid_hex(client):
    terr_engine = WolfCryptEngine()
    terr_pub, _ = terr_engine.dsa_keygen()
    client.post("/peer", json={"public_key_hex": terr_pub.hex()})

    resp = client.post("/uplink", json={"envelope_hex": "not-hex"})
    assert resp.status_code == 400


def test_downlink_data_stage_without_active_key_is_409(client):
    resp = client.post("/downlink/data/stage", json={"plaintext_b64": base64.b64encode(b"x").decode()})
    assert resp.status_code == 409


def test_downlink_data_without_anything_staged_is_404(client, monkeypatch):
    # Give it a traffic key by hand (bypassing the full handshake) purely to isolate
    # "no data queued" from "no key yet" — the full handshake path is covered by the
    # roundtrip test below.
    from origo_space import server

    monkeypatch.setattr(server, "_traffic_key", b"\x00" * 32)
    resp = client.post("/downlink/data")
    assert resp.status_code == 404


class TestFullRoundtrip:
    """One real ML-KEM-1024 + ML-DSA-87 handshake, then a multi-frame encrypted
    telemetry drain — the same two things the Docker device loop actually proves,
    exercised here in-process so it runs in CI without any containers at all."""

    def test_key_exchange_then_multi_frame_data_delivery(self, client):
        terr_engine = WolfCryptEngine()
        terr_pub, terr_priv = terr_engine.dsa_keygen()

        # 1. Provisioning ceremony's other half: Space learns the terrestrial peer's key.
        resp = client.post("/peer", json={"public_key_hex": terr_pub.hex()})
        assert resp.status_code == 200

        # 2. Space "transmits" a real, signed ek envelope.
        resp = client.post("/downlink/trigger")
        assert resp.status_code == 200
        envelope = parse_ek_envelope(bytes.fromhex(resp.json()["envelope_hex"]))
        assert envelope is not None

        # 3. Simulated terrestrial side: verify, encapsulate, sign — reproduced
        # directly against origo_crypto rather than importing origo_terrestrial.
        space_pub = bytes.fromhex(client.get("/identity").json()["public_key_hex"])
        assert terr_engine.dsa_verify(public_key=space_pub, message=envelope.ek, signature=envelope.signature)
        encaps = terr_engine.kem_encapsulate(envelope.ek)
        ct_signature = terr_engine.dsa_sign(private_key=terr_priv, message=encaps.ciphertext)
        ct_envelope = pack_ct_envelope(ciphertext=encaps.ciphertext, signature=ct_signature)
        terr_traffic_key = terr_engine.hkdf(shared_secret=encaps.shared_secret, context=HKDF_CONTEXT)

        # 4. Space receives the uplink and (per its own account) derives the same key.
        resp = client.post("/uplink", json={"envelope_hex": ct_envelope.hex()})
        assert resp.status_code == 200
        assert resp.json()["key_fingerprint"] == hashlib.sha256(terr_traffic_key).hexdigest()[:16]

        # 5. A second /uplink with the same (now-stale) envelope must not silently
        # succeed a second time — if this starts failing, agent.process_ct_envelope
        # gained real replay protection and this assertion should flip to expecting
        # a 4xx.
        resp = client.post("/uplink", json={"envelope_hex": ct_envelope.hex()})
        assert resp.status_code == 200, (
            "replay behavior changed — update this test's expectation, don't just "
            "make it pass"
        )

        # 6. Stage a payload spanning multiple chunks and drain it frame by frame.
        payload = b"telemetry-frame-" * 20   # > DATA_CHUNK_BYTES (200) -> >= 2 frames
        resp = client.post(
            "/downlink/data/stage", json={"plaintext_b64": base64.b64encode(payload).decode()},
        )
        assert resp.status_code == 200
        n_chunks = resp.json()["chunks_queued"]
        assert n_chunks >= 2
        assert client.get("/downlink/data/status").json() == {"chunks_queued": n_chunks}

        reassembled = b""
        for expected_seq in range(n_chunks):
            resp = client.post("/downlink/data")
            assert resp.status_code == 200
            body = resp.json()
            assert body["sequence_number"] == expected_seq
            # Raw ciphertext, no envelope/magic-byte wrapper — see module docstring.
            plaintext = terr_engine.aead_decrypt(
                key=terr_traffic_key, nonce=expected_seq.to_bytes(12, "big"),
                ciphertext=bytes.fromhex(body["ciphertext_hex"]),
            )
            reassembled += plaintext

        assert reassembled == payload

        # 7. Queue is now empty.
        assert client.get("/downlink/data/status").json() == {"chunks_queued": 0}
        resp = client.post("/downlink/data")
        assert resp.status_code == 404

    def test_stage_rejects_a_second_batch_before_the_first_drains(self, client):
        """The consumer's own sequence counter (pass_executor._run_data_delivery)
        resets to 0 for every fresh DATA_DELIVERY step — so this side's counter must
        too, or two overlapping batches would desync their nonces. Enforced by
        refusing a second /stage call while chunks remain, rather than silently
        producing ciphertext the second job's decrypt would fail to authenticate."""
        terr_engine = WolfCryptEngine()
        terr_pub, terr_priv = terr_engine.dsa_keygen()
        client.post("/peer", json={"public_key_hex": terr_pub.hex()})
        envelope = parse_ek_envelope(bytes.fromhex(client.post("/downlink/trigger").json()["envelope_hex"]))
        space_pub = bytes.fromhex(client.get("/identity").json()["public_key_hex"])
        terr_engine.dsa_verify(public_key=space_pub, message=envelope.ek, signature=envelope.signature)
        encaps = terr_engine.kem_encapsulate(envelope.ek)
        ct_envelope = pack_ct_envelope(
            ciphertext=encaps.ciphertext, signature=terr_engine.dsa_sign(private_key=terr_priv, message=encaps.ciphertext),
        )
        client.post("/uplink", json={"envelope_hex": ct_envelope.hex()})

        from origo_space.server import DATA_CHUNK_BYTES

        payload = base64.b64encode(b"x" * (DATA_CHUNK_BYTES + 1)).decode()
        first = client.post("/downlink/data/stage", json={"plaintext_b64": payload})
        assert first.status_code == 200

        second = client.post("/downlink/data/stage", json={"plaintext_b64": payload})
        assert second.status_code == 409