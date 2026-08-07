from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)

        subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "gen_proto.py"),
            ],
            check=True,
        )