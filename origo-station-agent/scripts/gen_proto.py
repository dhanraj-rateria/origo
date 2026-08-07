# origo-station-agent/scripts/gen_proto.py
"""Generate gRPC stubs from proto/origo/v1/origo.proto. Run via `make proto-origo`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = ROOT / "proto"
OUT_DIR = ROOT / "src" / "origo_station_agent" / "_proto"


def main() -> int:
    protos = sorted(PROTO_DIR.rglob("*.proto"))
    if not protos:
        print(f"no .proto files under {PROTO_DIR}", file=sys.stderr)
        return 1
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={PROTO_DIR}", f"--python_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}", f"--pyi_out={OUT_DIR}",
        *(str(p) for p in protos),
    ]
    subprocess.run(cmd, check=True)
    for d in [OUT_DIR, *(p for p in OUT_DIR.rglob("*") if p.is_dir())]:
        (d / "__init__.py").touch(exist_ok=True)
    print(f"generated {len(protos)} protos -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())