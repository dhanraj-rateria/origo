# origo-terrestrial/scripts/gen_proto.py
"""Generate gRPC stubs from proto/origo/v1/origo.proto.

Same .proto contract as origo-station-agent/proto/origo/v1/origo.proto, duplicated on
purpose — origo-station-agent generates the *client* stub from its copy, this
generates the *server* stub (OrigoTerrestrialServiceServicer, which service.py
subclasses) from this one. Same rationale as origo_crypto/envelope.py's wire-format
duplication: the two sides shouldn't depend on each other's package, so the contract
is specified independently in both places. If either .proto changes, both must change
together.

Run via `python scripts/gen_proto.py` (no Makefile target yet — add one alongside
`proto-origo` if this starts getting run often enough to be worth it).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
import re

_ABS_IMPORT_RE = re.compile(r"^from [\w.]+ import (\w+_pb2) as ", re.MULTILINE)

ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = ROOT / "proto"
OUT_DIR = ROOT / "src" / "origo_terrestrial" / "_proto"

def _fix_relative_imports(out_dir: Path) -> None:
    """protoc's Python gRPC plugin emits an *absolute* import for the sibling pb2
    module (`from origo.v1 import origo_pb2 as ...`), matching the proto's package
    name as if it were a real top-level Python package. It isn't — this output lives
    nested under our own package, imported relatively everywhere else. Standard
    protoc/grpc_tools gotcha; rewriting it to a same-directory relative import is the
    standard fix."""
    for grpc_file in out_dir.rglob("*_pb2_grpc.py"):
        text = grpc_file.read_text()
        fixed = _ABS_IMPORT_RE.sub(r"from . import \1 as ", text)
        if fixed != text:
            grpc_file.write_text(fixed)

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
    _fix_relative_imports(OUT_DIR)
    for d in [OUT_DIR, *(p for p in OUT_DIR.rglob("*") if p.is_dir())]:
        (d / "__init__.py").touch(exist_ok=True)
    print(f"generated {len(protos)} protos -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
