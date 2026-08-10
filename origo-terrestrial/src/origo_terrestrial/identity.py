# origo-terrestrial-sw/src/origo_terrestrial_sw/identity.py
"""Dev-simplicity provisioning: each side's own keypair persists to a local file; the
peer's public key is a config value someone copies over by hand. This is deliberately
the software-prototype stand-in for design §9's provisioning ceremony — there's no live
channel to fetch a peer key over, so pre-provisioning is the correct mental model even
here, just simplified to a JSON file instead of a real ceremony."""

from __future__ import annotations

import json
from pathlib import Path

from origo_crypto.engine import CryptoEngine


class IdentityStore:
    def __init__(self, *, path: Path, engine: CryptoEngine) -> None:
        self._path = path
        self._engine = engine
        if path.exists():
            data = json.loads(path.read_text())
            self.public_key = bytes.fromhex(data["public_key"])
            self.private_key = bytes.fromhex(data["private_key"])
        else:
            self.public_key, self.private_key = engine.dsa_keygen()
            path.write_text(json.dumps({
                "public_key": self.public_key.hex(), "private_key": self.private_key.hex(),
            }))
            print(f"generated new identity, public key (share this with the peer):\n{self.public_key.hex()}")